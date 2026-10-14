"""The textures the Bedrock pack's blocks are drawn with.

Each Java texture a converted face uses is written once to
`textures/java/<namespace>/<path>.png` and named in `terrain_texture.json`,
the atlas Bedrock's block materials pick their textures from. A face Java
tints by a fixed colour (or every tinted face, with `"tint": "baked"`) gets a
tinted copy under `textures/java_tinted/<rrggbb>/`.

A texture animated by its `.png.mcmeta` becomes a flipbook
(`flipbook_textures.json`): Bedrock steps through square frames stacked from
the top, so frames laid out otherwise are restacked, and a frame list with
times of its own is spelt out frame by frame, as Rainbow does.

The render method follows the texture, as Java's does since 1.21.5: opaque
pixels only draw opaque, fully clear pixels need alpha testing, and anything
in between blends. Java draws only the front of a block's faces, so do these.
"""

import json
import math
from dataclasses import dataclass
from pathlib import Path

from java_pack import Assets, split_identifier
from PIL import Image

OPAQUE = "opaque"
ALPHA_TEST = "alpha_test_single_sided"
BLEND = "blend"
# A block's materials share the most see-through method any of them needs
RENDER_ORDER = (OPAQUE, ALPHA_TEST, BLEND)


@dataclass
class _Source:
    path: Path
    from_pack: bool
    size: tuple[int, int]
    render_method: str
    # (frame width, frame height, Java frame list of (index, time), frametime, interpolate)
    animation: tuple | None


class TextureStore:
    def __init__(self, assets: Assets, warn):
        self.assets = assets
        self.warn = warn
        self._sources: dict[str, _Source | None] = {}
        # terrain key -> (texture identifier, tint colour or None)
        self._used: dict[str, tuple[str, int | None]] = {}

    def source(self, texture: str) -> _Source | None:
        """What's known about a texture identifier, or None when it can't be found."""
        if texture not in self._sources:
            self._sources[texture] = self._load(texture)
        return self._sources[texture]

    def _load(self, texture: str) -> _Source | None:
        found = self.assets.texture(texture)
        if found is None:
            self.warn(f"Missing texture file: {texture}")
            return None
        path, from_pack = found
        try:
            with Image.open(path) as image:
                image = image.convert("RGBA")
                size = image.size
                alpha = image.getchannel("A").histogram()
        except OSError as e:
            self.warn(f"Couldn't read texture {texture}: {e}")
            return None
        if any(alpha[1:255]):
            method = BLEND
        elif alpha[0]:
            method = ALPHA_TEST
        else:
            method = OPAQUE
        return _Source(path, from_pack, size, method, self._animation(texture, path, size))

    def _animation(self, texture: str, path: Path, size):
        meta_path = Path(str(path) + ".mcmeta")
        if not meta_path.is_file():
            return None
        meta = self.assets.read_json(meta_path)
        animation = meta.get("animation") if isinstance(meta, dict) else None
        if not isinstance(animation, dict):
            return None
        width, height = size
        if "width" in animation or "height" in animation:
            frame = (int(animation.get("width", width)), int(animation.get("height", height)))
        else:
            frame = (min(width, height),) * 2
        if frame[0] <= 0 or frame[1] <= 0 or frame[0] != frame[1]:
            self.warn(f"{texture} is animated with frames of {frame[0]}x{frame[1]}; Bedrock animates square frames only, so it shows its first frame")
            return None
        count = (width // frame[0]) * (height // frame[1])
        frametime = max(1, int(animation.get("frametime", 1)))
        frames = []
        for entry in animation.get("frames", range(count)):
            index = entry["index"] if isinstance(entry, dict) else entry
            time = entry.get("time", frametime) if isinstance(entry, dict) else frametime
            if isinstance(index, int) and 0 <= index < count:
                frames.append((index, max(1, int(time))))
        if count < 2 or not frames:
            return None
        return (frame[0], frame[1], frames, frametime, bool(animation.get("interpolate", False)))

    def render_method(self, texture: str) -> str:
        source = self.source(texture)
        return source.render_method if source else OPAQUE

    def use(self, texture: str, colour: int | None = None) -> str | None:
        """The terrain atlas name a material uses for the texture, tinted by `colour`."""
        if self.source(texture) is None:
            return None
        namespace, path = split_identifier(texture)
        key = "java." + namespace + "." + path.replace("/", ".")
        if colour is not None:
            key += f".tint_{colour:06x}"
        self._used[key] = (texture, colour)
        return key

    def count(self) -> int:
        return len(self._used)

    # ----------------------------------------------------------------------

    def write(self, root: Path, pack_name: str):
        """Every used texture into the pack, with terrain_texture.json and flipbook_textures.json."""
        terrain, flipbooks = {}, []
        for key, (texture, colour) in sorted(self._used.items()):
            source = self._sources[texture]
            namespace, path = split_identifier(texture)
            folder = "textures/java" if colour is None else f"textures/java_tinted/{colour:06x}"
            relative = f"{folder}/{namespace}/{path}"
            target = root / (relative + ".png")
            target.parent.mkdir(parents=True, exist_ok=True)
            with Image.open(source.path) as image:
                image = image.convert("RGBA")
                if source.animation is not None:
                    image = _vertical_strip(image, source.animation[0], source.animation[1])
                if colour is not None:
                    image = _tinted(image, colour)
                image.save(target)
            terrain[key] = {"textures": relative}
            if source.animation is not None:
                flipbooks.append(_flipbook(key, relative, source.animation))
        textures = root / "textures"
        textures.mkdir(parents=True, exist_ok=True)
        _write_json(
            textures / "terrain_texture.json",
            {
                "resource_pack_name": pack_name,
                "texture_name": "atlas.terrain",
                "padding": 8,
                "num_mip_levels": 4,
                "texture_data": terrain,
            },
        )
        if flipbooks:
            _write_json(textures / "flipbook_textures.json", flipbooks)


def _vertical_strip(image: Image.Image, frame_width: int, frame_height: int) -> Image.Image:
    """The frames, in Java's order (left to right, then down), stacked from the top."""
    columns = image.width // frame_width
    rows = image.height // frame_height
    if columns == 1:
        return image.crop((0, 0, frame_width, rows * frame_height))
    strip = Image.new("RGBA", (frame_width, columns * rows * frame_height))
    for i in range(columns * rows):
        x, y = (i % columns) * frame_width, (i // columns) * frame_height
        strip.paste(image.crop((x, y, x + frame_width, y + frame_height)), (0, i * frame_height))
    return strip


def _tinted(image: Image.Image, colour: int) -> Image.Image:
    """The image multiplied by a colour, as Java's tint multiplies a face's texture."""
    r, g, b, a = image.split()
    factors = ((colour >> 16) & 255, (colour >> 8) & 255, colour & 255)
    channels = [c.point(lambda v, f=f: v * f // 255) for c, f in zip((r, g, b), factors)]
    return Image.merge("RGBA", (*channels, a))


def _flipbook(key: str, relative: str, animation) -> dict:
    _, _, frames, frametime, interpolate = animation
    step = math.gcd(*(time for _, time in frames))
    entry = {"flipbook_texture": relative, "atlas_tile": key, "ticks_per_frame": step}
    sequence = [index for index, time in frames for _ in range(time // step)]
    if sequence != list(range(len(sequence))):
        entry["frames"] = sequence
    if interpolate:
        entry["blend_frames"] = True
    return entry


def _write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
