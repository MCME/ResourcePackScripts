"""Build a pack's release zip with PackSquash, and check it.

    python release/squash.py vanilla <pack folder> <zip>
    python release/squash.py sodium  <pack folder> <zip>

PackSquash (https://github.com/ComunidadAylas/PackSquash, tested with v0.4.1)
is found through --packsquash, then the PACKSQUASH environment variable, then
the PATH. The zip it writes is checked against the pack, and the script fails
if anything that changes how the pack renders was lost on the way.

What PackSquash may and may not do here:
- Ordinary textures are colour-quantized where it saves space - lossy, but
  hard to tell apart in game.
- objmc bakes (the vanilla pack's assets/mcme textures) carry geometry in
  their pixels and are never quantized. Neither are labPBR normal and
  specular maps (*_n.png, *_s.png), which store material values, not colours.
- Fully transparent texels may be recoloured, like the client does as it
  loads the atlas - except in labPBR maps, whose alpha is data.
- Shaders are copied as they are: ours rely on #moj_import and #define.
- Identical files are stored once (zip_spec_conformance_level 'balanced'):
  Minecraft reads such a zip, some zip tools - Python's among them - don't.

PackSquash gotchas this works around:
- It decides between overlapping file patterns by sorting them, first match
  winning - not by their order in the file. A pattern like '**/*.png' sorts
  before every 'assets/...' one and would win over all of them.
- A PNG no pattern matches is quantized by default.
- It reuses an earlier run's output zip, even under changed options, so the
  zip is always deleted first.
- It skips files it doesn't know: the Sodium pack's .obj, .mtl and .objmeta
  are forced in, and license.txt and texture.properties (allow_mods =
  ['OptiFine'] only lets OptiFine's model files through).
"""

import argparse
import io
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile
import zlib
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "generateVanilla"))
import objmc_decode  # noqa: E402

# What a release holds, from the pack folder's top level. Everything else -
# the vanilla overrides folder, version overlays the pack doesn't declare,
# editor folders - stays out.
RELEASED = ("assets", "pack.mcmeta", "pack.png", "license.txt")

# PackSquash's options, as TOML: settings for the whole pack, then the file
# patterns. A setting after a pattern's [header] belongs to that pattern.
GLOBAL_OPTIONS = """
zip_spec_conformance_level = 'balanced'
"""

FILE_OPTIONS = """
['**/*.{fsh,glsl,vsh}']
shader_source_transformation_strategy = 'keep_as_is'

['license.txt']
force_include = true
"""

VARIANTS = {
    "vanilla": {
        # OptiFine-only files. block.properties would even move blocks
        # carrying objmc models into other render layers.
        "leave_out": ("assets/minecraft/optifine/",),
        "global_options": "",
        "file_options": """
['assets/mcme/**/*.png']
color_quantization_target = 'none'

['assets/minecraft/**/*.png']
color_quantization_target = 'auto'

['assets/modelengine/**/*.png']
color_quantization_target = 'auto'
""",
    },
    "sodium": {
        # OptiFine-only, and written for old block and texture names.
        # texture.properties stays: it tells shader packs the labPBR format.
        "leave_out": (
            "assets/minecraft/optifine/bettergrass.properties",
            "assets/minecraft/optifine/block.properties",
        ),
        "global_options": "",
        "file_options": """
['**/*.{mtl,obj,objmeta}']
force_include = true

['assets/minecraft/optifine/texture.properties']
force_include = true

['**/*_n.png']
color_quantization_target = 'none'
skip_alpha_optimizations = true

['**/*_s.png']
color_quantization_target = 'none'
skip_alpha_optimizations = true
""",
    },
}

# Files whose bytes must come through exactly.
EXACT = (".fsh", ".glsl", ".vsh", ".obj", ".mtl", ".objmeta", ".properties")


def needed(path):
    """Whether the game reads a file like this - losing one fails the check."""
    if path in ("license.txt", "pack.png", "pack.mcmeta"):
        return True
    if path.endswith(".png"):
        return "/textures/" in path
    return path.endswith(EXACT + (".json", ".mcmeta"))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("variant", choices=sorted(VARIANTS))
    parser.add_argument("pack", type=Path, help="the pack folder")
    parser.add_argument("zip", type=Path, help="the release zip to write")
    parser.add_argument("--packsquash", help="the PackSquash executable")
    args = parser.parse_args(argv)
    packsquash = args.packsquash or os.environ.get("PACKSQUASH") or shutil.which("packsquash")
    if not packsquash:
        parser.error("PackSquash not found: pass --packsquash or set PACKSQUASH")

    variant = VARIANTS[args.variant]
    with tempfile.TemporaryDirectory(prefix="squash-", ignore_cleanup_errors=True) as temp:
        staged = Path(temp) / "pack"
        stage(args.pack, staged, variant["leave_out"])
        options = Path(temp) / "options.toml"
        options.write_text(
            f"pack_directory = '{staged.as_posix()}'\n"
            f"output_file_path = '{args.zip.resolve().as_posix()}'\n"
            + GLOBAL_OPTIONS + variant["global_options"]
            + FILE_OPTIONS + variant["file_options"],
            encoding="utf-8",
        )
        args.zip.unlink(missing_ok=True)
        args.zip.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run([packsquash, str(options)], capture_output=True, text=True)
        if result.returncode != 0 or not args.zip.exists():
            print(result.stdout[-4000:], result.stderr[-4000:], sep="\n")
            sys.exit(f"PackSquash failed (exit {result.returncode})")

        problems = check(staged, args.zip, args.variant)
    size = args.zip.stat().st_size / 1e6
    if problems:
        print("\n".join(problems))
        sys.exit(f"{args.zip} ({size:.1f} MB) FAILED its check - don't release it")
    print(f"{args.zip}: {size:.1f} MB, checked")


def stage(pack: Path, staged: Path, leave_out):
    for name in RELEASED:
        source = pack / name
        if source.is_dir():
            shutil.copytree(source, staged / name)
        elif source.is_file():
            staged.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, staged / name)
    for path in leave_out:
        target = staged / path
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink(missing_ok=True)


# --------------------------------------------------------------------------
# Checking the zip
# --------------------------------------------------------------------------


class LenientZip:
    """A zip read by its central directory only, as Minecraft reads it - so
    entries sharing one stored copy (PackSquash's deduplication) read fine."""

    def __init__(self, path):
        self.file = open(path, "rb")
        self.entries = {i.filename: i for i in zipfile.ZipFile(path).infolist()}

    def read(self, name):
        entry = self.entries[name]
        self.file.seek(entry.header_offset)
        header = self.file.read(30)
        name_length, extra_length = struct.unpack("<HH", header[26:30])
        self.file.seek(entry.header_offset + 30 + name_length + extra_length)
        data = self.file.read(entry.compress_size)
        return zlib.decompress(data, -15) if entry.compress_type == zipfile.ZIP_DEFLATED else data


def _pixels(data, keep_hidden):
    image = Image.open(io.BytesIO(data)).convert("RGBA")
    return image.tobytes() if keep_hidden else objmc_decode.visible_bytes(image)


def check(staged: Path, zip_path: Path, variant) -> list:
    z = LenientZip(zip_path)
    files = sorted(p.relative_to(staged).as_posix() for p in staged.rglob("*") if p.is_file())
    problems = []

    lost = [f for f in files if f not in z.entries and needed(f)]
    problems += [f"lost: {f}" for f in lost]
    left = [f for f in files if f not in z.entries and f not in lost]
    if left:
        print(f"PackSquash left out {len(left)} files the game doesn't read, e.g. {left[:3]}")

    for f in files:
        if f not in z.entries:
            continue
        ours, theirs = (staged / f).read_bytes(), z.read(f)
        if (f.endswith(EXACT) or f == "license.txt") and ours != theirs:
            problems.append(f"changed: {f}")
        elif f.endswith((".json", ".mcmeta")):
            try:
                json.loads(theirs.decode("utf-8-sig"))
            except ValueError:
                problems.append(f"unreadable JSON: {f}")
        elif f.endswith(".png") and _lossless(f, variant):
            hidden = f.endswith(("_n.png", "_s.png"))
            try:
                if _pixels(ours, hidden) != _pixels(theirs, hidden):
                    problems.append(f"pixels changed: {f}")
            except OSError:
                pass  # a PNG PIL can't read either way

    if variant == "vanilla":
        problems += _check_carriers(staged, z)
    return problems


def _lossless(path, variant):
    if path.endswith(("_n.png", "_s.png")):
        return True
    return variant == "vanilla" and path.startswith("assets/mcme/")


def _check_carriers(staged: Path, z: LenientZip) -> list:
    """Every objmc carrier decodes from the zip as from the pack."""
    models = {}
    for file in (staged / "assets").glob("*/models/**/*.json"):
        namespace, _, rest = file.relative_to(staged / "assets").as_posix().partition("/")
        try:
            models[f"{namespace}:{rest[len('models/'):-len('.json')]}"] = json.loads(
                file.read_text(encoding="utf-8-sig")
            )
        except ValueError:
            continue

    def full(identifier):
        return identifier if ":" in identifier else "minecraft:" + identifier

    def texture(identifier, source):
        namespace, path = full(identifier).split(":", 1)
        name = f"assets/{namespace}/textures/{path}.png"
        data = (staged / name).read_bytes() if source == "pack" else z.read(name)
        return Image.open(io.BytesIO(data)).convert("RGBA")

    problems, checked = [], 0
    cache = {}
    for identifier, data in models.items():
        textures, elements, model, seen = dict(data.get("textures") or {}), data.get("elements"), data, set()
        while elements is None and isinstance(model.get("parent"), str) and full(model["parent"]) in models:
            if model["parent"] in seen:
                break
            seen.add(model["parent"])
            model = models[full(model["parent"])]
            textures = {**(model.get("textures") or {}), **textures}
            elements = model.get("elements")
        bake = textures.get("0")
        if not elements or not isinstance(bake, str) or bake.startswith("#"):
            continue
        try:
            for source in ("pack", "zip"):
                if (bake, source) not in cache:
                    cache[(bake, source)] = texture(bake, source)
            before = objmc_decode.decode_model(cache[(bake, "pack")], elements)
        except (OSError, KeyError, IndexError, AssertionError):
            continue  # not an objmc model
        if not before:
            continue
        checked += 1
        try:
            after = objmc_decode.decode_model(cache[(bake, "zip")], elements)
        except (IndexError, AssertionError):
            after = None
        if after != before:
            problems.append(f"objmc model broken: {identifier}")
    if not problems:
        print(f"{checked} objmc models decode as in the pack")
    return problems


if __name__ == "__main__":
    main()
