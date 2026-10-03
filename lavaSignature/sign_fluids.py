"""Writes the fluids' codes into a pack's lava and water textures, so its shaders know them.

The Mordor pack's terrain shaders draw lava and water themselves
(assets/minecraft/shaders/include/fluid.glsl, lava.glsl, water.glsl), on
whatever shows block/lava_still, lava_flow, water_still, water_flow, ice, fog,
spray, or the tar's powder_snow textures. They
tell those apart from every other texture by a code in the lowest two bits of
each texel's red, green and blue: 6 bits, set by the texel's place in its 4x4
block of the sprite and by which sprite it is. That changes no colour by more
than 3 steps in 255; alpha is left as it is.

Editing one of these textures loses the codes, and the shaders then show it as
a plain texture. Run this after every edit:

    python sign_fluids.py <pack folder>
    python sign_fluids.py <pack folder> --check

--check only reports whether the textures carry their codes. The textures must
be as wide and as tall a frame as a multiple of 4 pixels, not interpolated
(their .mcmeta), which would blend the codes away, and lava's and tar's opaque;
the others' texels need some alpha. Release zips must keep their pixels exactly.
"""

import argparse
import json
import sys
from pathlib import Path

from PIL import Image

# fluid.glsl's FLUID_ kinds, by texture
TEXTURES = {"lava_still": 0, "lava_flow": 1, "water_still": 2, "water_flow": 3, "ice": 4, "fog": 5,
            "powder_snow": 6, "powder_snow_2": 6, "powder_snow_3": 6, "powder_snow_4": 6,
            "spray": 7}
OPAQUE = {"lava_still", "lava_flow", "powder_snow", "powder_snow_2", "powder_snow_3", "powder_snow_4"}
FOLDER = Path("assets/minecraft/textures/block")
M = 0xFFFFFFFF


def fluid_hash(x, y, z, w):
    """fluid.glsl's fluidHash()."""
    h = ((x * 73856093) ^ (y * 19349663) ^ (z * 83492791) ^ (w * 2654435761)) & M
    h ^= h >> 13
    h = (h * 0x5BD1E995) & M
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


def signed(image, kind):
    pixels = image.load()
    return all(
        (pixels[x, y][3] == 255 if kind in (0, 1, 6) else pixels[x, y][3] > 0)
        and ((pixels[x, y][0] & 3) << 4 | (pixels[x, y][1] & 3) << 2 | (pixels[x, y][2] & 3)) == fluid_code(kind, x, y)
        for y in range(image.height)
        for x in range(image.width)
    )


def problems(image, path, opaque):
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
        found.append(f"{meta.name} interpolates its frames")
    return found


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("pack", type=Path, help="the pack folder")
    parser.add_argument("--check", action="store_true", help="only report whether they carry their codes")
    args = parser.parse_args(argv)

    failed = False
    for name, kind in TEXTURES.items():
        path = args.pack / FOLDER / f"{name}.png"
        if not path.is_file():
            # (not every branch of the pack has every one: the fog's and the
            # spray's are on their own)
            print(f"{path}: not in this pack, skipped")
            continue
        image = Image.open(path)
        if image.mode != "RGBA":
            image = image.convert("RGBA")
        wrong = problems(image, path, name in OPAQUE)
        if wrong:
            print("\n".join(wrong))
            failed = True
            continue
        if args.check:
            ok = signed(image, kind)
            print(f"{path}: {'signed' if ok else 'NOT signed'}")
            failed |= not ok
        elif signed(image, kind):
            print(f"{path}: already signed")
        else:
            sign(image, kind)
            image.save(path)
            print(f"{path}: signed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
