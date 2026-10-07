"""The fluids' codes in their textures, which the terrain shaders know them by.

The shader base draws water itself, and a pack may draw other fluids (RP-
Mordor's lava and ice), on whatever shows block/water_still, water_flow,
lava_still, lava_flow or ice. fluid.glsl tells those apart from every other texture by a code
in the lowest two bits of each texel's red, green and blue: 6 bits, set by the
texel's place in its 4x4 block of the sprite and by which sprite it is. That
changes no colour by more than 3 steps in 255; alpha is left as it is.

Editing one of these textures loses the codes, and the shaders then show it as
a plain texture. The build signs every pack's water (shader_base.finish); a
pack's own fluids are signed in its repository with signFluids.py.
"""

import json
from pathlib import Path

from PIL import Image

# fluid.glsl's FLUID_ kinds, by texture
# (5 to 7 are a pack's own: RP-Mordor signs its fog, tar and spray itself)
KINDS = {"lava_still": 0, "lava_flow": 1, "water_still": 2, "water_flow": 3, "ice": 4}
WATER = ("water_still", "water_flow")
LAVA = ("lava_still", "lava_flow")
ICE = ("ice",)
OPAQUE = set(LAVA)
FOLDER = Path("assets/minecraft/textures/block")
_M = 0xFFFFFFFF


def fluid_hash(x, y, z, w):
    """fluid.glsl's fluidHash()."""
    h = ((x * 73856093) ^ (y * 19349663) ^ (z * 83492791) ^ (w * 2654435761)) & _M
    h ^= h >> 13
    h = (h * 0x5BD1E995) & _M
    h ^= h >> 15
    return h


def fluid_code(kind, x, y):
    """fluid.glsl's fluidCode(): the 6 bits the texel at x, y holds."""
    return fluid_hash(x & 3, y & 3, kind, 731) >> 26


def sign(image, kind):
    pixels = image.load()
    for y in range(image.height):
        for x in range(image.width):
            r, g, b, a = pixels[x, y]
            code = fluid_code(kind, x, y)
            pixels[x, y] = ((r & ~3) | (code >> 4), (g & ~3) | ((code >> 2) & 3), (b & ~3) | (code & 3), a)


def is_signed(image, kind):
    pixels = image.load()
    opaque = kind in (KINDS[n] for n in OPAQUE)
    return all(
        (pixels[x, y][3] == 255 if opaque else pixels[x, y][3] > 0)
        and ((pixels[x, y][0] & 3) << 4 | (pixels[x, y][1] & 3) << 2 | (pixels[x, y][2] & 3))
        == fluid_code(kind, x, y)
        for y in range(image.height)
        for x in range(image.width)
    )


def problems(image, path: Path, opaque) -> list[str]:
    """Why the texture can't carry its codes, if it can't."""
    found = []
    if image.width % 4:
        found.append(f"{path.name} is {image.width} wide, not a multiple of 4")
    if image.height % 4:
        found.append(f"{path.name} is {image.height} tall, not a multiple of 4")
    if opaque and image.getextrema()[3][0] < 255:
        found.append(f"{path.name} isn't opaque")
    if not opaque and image.getextrema()[3][0] == 0:
        found.append(f"{path.name} has fully transparent texels, which can't carry a code")
    meta = path.with_name(path.name + ".mcmeta")
    if meta.is_file() and json.loads(meta.read_text(encoding="utf-8-sig")).get("animation", {}).get("interpolate"):
        found.append(f"{meta.name} interpolates its frames, which blends the codes away")
    return found


def sign_pack(pack_path, names, check=False, kinds=None) -> tuple[list[str], bool]:
    """Sign (or with check, only check) the pack's textures of these names -
    the base's fluids (KINDS), or a pack's own, by kinds (name: 5 to 7).

    Returns what was done to each, and whether everything is signed. A texture
    the pack doesn't have is passed over: the game's own then shows, plain.
    """
    messages = []
    ok = True
    for name in names:
        path = Path(pack_path) / FOLDER / f"{name}.png"
        if not path.is_file():
            continue
        kind = (kinds or {}).get(name, KINDS.get(name))
        image = Image.open(path)
        if image.mode != "RGBA":
            image = image.convert("RGBA")
        wrong = problems(image, path, name in OPAQUE)
        if wrong:
            messages += wrong
            ok = False
        elif is_signed(image, kind):
            messages.append(f"{path}: signed")
        elif check:
            messages.append(f"{path}: NOT signed")
            ok = False
        else:
            sign(image, kind)
            image.save(path)
            messages.append(f"{path}: signed now")
    return messages, ok
