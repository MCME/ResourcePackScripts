"""Merge the objmc bakes that hold the same texture into one sprite.

objmc bakes one sprite per model: a header, the face pointers, the texture and
the geometry data. Models sharing a texture - a model's variants, every
rotation of each - each carried their own copy of it, which made the textures
most of the pack's size and of the block atlas. Once every model is converted,
the bakes with the same texture are rewritten into one sprite: the texture once
at the top, then each model's own block of header, pointers and data. The
header says how far up the texture is (layout 2 in objmc_main.glsl), and each
model's carriers are moved to its block's pointers.

A shared parent's carriers ("*_parent", see objmc_conversion) point into one
bake's layout, and each model's block now sits at its own place in its own
sprite, so every model gets its own copy of them, and the parents nothing uses
any more are removed. Flipbooks are left as they are: every frame would need a
copy of every model's data.
"""

import copy
import json
import math
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

import constants
import util
from objmc_conversion import _bake_texture_rows, _write_model

# objmc's header marker, t[0].
MARKER = (12, 34, 56, 255)
# t[8].r of a header whose texture is shared, above it; 0 in objmc's own bakes.
SHARED_LAYOUT = 2
# How far up the texture may be, in rows: t[8].g and t[8].b.
MAX_TEXTURE_DISTANCE = 65535
# The tallest sprite made; a group that would be taller is split. The client
# stitches the atlas no larger than the GPU allows, often 16384.
MAX_SPRITE_HEIGHT = 8192


@dataclass
class _Bake:
    path: Path
    identifier: str
    width: int
    texture_height: int
    mipmap: int
    # The bake's own height, which its carriers' UVs are fractions of.
    height: int
    texture: Image.Image
    # The header row, the clock row and the face pointers, then the data.
    block: Image.Image


def merge_shared_textures(output_path, compress, debug):
    output_path = Path(output_path)
    bakes = _find_bakes(output_path)
    groups = {}
    for bake in bakes.values():
        key = (bake.width, bake.texture_height, bake.mipmap, bake.texture.tobytes())
        groups.setdefault(key, []).append(bake)

    # bake identifier -> (sprite identifier, the block's first row, sprite height)
    moved = {}
    sprites = 0
    for group in groups.values():
        if len(group) < 2:
            continue
        group.sort(key=lambda b: b.identifier)
        for part in _split(group):
            sprite, rows = _merge(part)
            sprite.save(part[0].path)
            sprites += 1
            for bake in part:
                moved[bake.identifier] = (part[0].identifier, rows[bake.identifier], sprite.height)

    if not moved:
        return
    print(
        f"Merged {len(moved)} objmc bakes holding the same texture into {sprites} sprites",
        flush=True,
    )
    inlined = _move_carriers(output_path, bakes, moved, compress, debug)
    _remove_unused(output_path, bakes, moved, inlined)


# --------------------------------------------------------------------------
# Reading the bakes
# --------------------------------------------------------------------------


def _texture_identifier(output_path: Path, png: Path) -> str:
    namespace, _, rest = png.relative_to(output_path / "assets").as_posix().partition("/")
    path = rest[len("textures/"):-len(constants.TEXTURE_EXTENSION)]
    return f"{namespace}:{path}"


def _find_bakes(output_path: Path) -> dict:
    bakes = {}
    for png in sorted((output_path / "assets").glob("*/textures/**/*" + constants.TEXTURE_EXTENSION)):
        if Path(str(png) + constants.MCMETA_EXTENSION).exists():
            continue  # a flipbook, or animated some other way
        identifier = _texture_identifier(output_path, png)
        bake = _read_bake(png, identifier)
        if bake is not None:
            bakes[identifier] = bake
    return bakes


def _read_bake(path: Path, identifier: str):
    """The bake at path, or None for anything that is not one of objmc's own
    single-texture bakes, laid out as objmc lays it out."""
    try:
        with Image.open(path) as image:
            if image.width < 16 or image.height < 2:
                return None
            bake = image.convert("RGBA")
    except (OSError, ValueError):
        return None  # not an image PIL can read, so not a bake either
    t = [bake.getpixel((x, 0)) for x in range(16)]
    if t[0] != MARKER or t[8][0] != 0:
        return None
    width = t[1][0] * 256 + t[1][1]
    texture_height = t[1][2] * 256 + t[7][0]
    vertex_count = t[2][0] * 16777216 + t[2][1] * 65536 + t[2][2] * 256 + t[7][1]
    frames = t[3][0] * 65536 + t[3][1] * 256 + t[3][2]
    # objmc writes one texture as 255 (objmc.py's POINTER_ALPHA)
    textures = 1 if t[3][3] == 255 else max(t[3][3], 1)
    if width != bake.width or max(frames, 1) != 1 or textures != 1:
        return None
    mipmap = t[6][1]
    position_rows = t[5][0] * 256 + t[5][1]
    uv_rows = t[5][2] * 256 + t[7][2]
    vertex_rows = math.ceil(vertex_count * 2 / width)
    pointers_end = 2 + math.ceil(vertex_count / 4 / width)
    _, top, data_top = _bake_texture_rows(pointers_end, texture_height, mipmap)
    data_end = data_top + position_rows + uv_rows + vertex_rows
    if top + texture_height > data_top or data_end > bake.height:
        return None

    block = Image.new("RGBA", (width, pointers_end + data_end - data_top))
    block.paste(bake.crop((0, 0, width, pointers_end)), (0, 0))
    block.paste(bake.crop((0, data_top, width, data_end)), (0, pointers_end))
    return _Bake(
        path=path,
        identifier=identifier,
        width=width,
        texture_height=texture_height,
        mipmap=mipmap,
        height=bake.height,
        texture=bake.crop((0, top, width, top + texture_height)),
        block=block,
    )


# --------------------------------------------------------------------------
# Laying out a merged sprite
# --------------------------------------------------------------------------


def _texture_rows(bake: _Bake):
    """(first texture row, first block row) of a merged sprite: the texture on a
    2^mipmap row boundary with at least one such block of its edge rows either
    side, as objmc pads it - so no mip level up to its mipmap mixes in a header
    or data."""
    if bake.mipmap <= 0:
        return 0, bake.texture_height
    rows = 1 << bake.mipmap
    return rows, -(-(rows + bake.texture_height) // rows) * rows + rows


def _split(group: list) -> list:
    """The group in parts that each fit one sprite."""
    top, first_block = _texture_rows(group[0])
    parts, part, y = [], [], first_block
    for bake in group:
        fits = y + bake.block.height <= MAX_SPRITE_HEIGHT and y - top <= MAX_TEXTURE_DISTANCE
        if part and not fits:
            parts.append(part)
            part, y = [], first_block
        part.append(bake)
        y += bake.block.height
    parts.append(part)
    return parts


def _merge(bakes: list):
    """The sprite holding the bakes' texture once and each bake's block, and
    each block's first row."""
    first = bakes[0]
    top, y = _texture_rows(first)
    rows = {}
    for bake in bakes:
        rows[bake.identifier] = y
        y += bake.block.height
    # A multiple of 16, like every bake: the client mipmaps the atlas no
    # further than its sprites' sizes allow.
    sprite = Image.new("RGBA", (first.width, -(-y // 16) * 16))

    sprite.paste(first.texture, (0, top))
    first_row = first.texture.crop((0, 0, first.width, 1))
    last_row = first.texture.crop((0, first.texture_height - 1, first.width, first.texture_height))
    for row in range(0, top):
        sprite.paste(first_row, (0, row))
    for row in range(top + first.texture_height, rows[first.identifier]):
        sprite.paste(last_row, (0, row))

    for bake in bakes:
        row = rows[bake.identifier]
        sprite.paste(bake.block, (0, row))
        distance = row - top
        sprite.putpixel((8, row), (SHARED_LAYOUT, distance // 256, distance % 256, 255))
    return sprite, rows


# --------------------------------------------------------------------------
# Moving the carriers
# --------------------------------------------------------------------------


def _read_models(output_path: Path) -> dict:
    models = {}
    for file in (output_path / "assets").glob("*/models/**/*" + constants.VANILLA_MODEL_EXTENSION):
        namespace, _, rest = file.relative_to(output_path / "assets").as_posix().partition("/")
        identifier = f"{namespace}:{rest[len('models/'):-len(constants.VANILLA_MODEL_EXTENSION)]}"
        try:
            with open(file, "r", encoding="utf-8-sig") as f:
                models[identifier] = (file, json.load(f))
        except (OSError, ValueError):
            continue
    return models


def _full_identifier(identifier: str) -> str:
    namespace, path = util.split_namespaced(identifier)
    return f"{namespace}:{path}"


def _move_carriers(output_path: Path, bakes: dict, moved: dict, compress, debug) -> set:
    """Point every model on a merged bake at its sprite and block. Returns the
    parents whose carriers were copied into the models borrowing them."""
    models = _read_models(output_path)
    inlined = set()
    for identifier, (file, data) in models.items():
        textures = data.get("textures") or {}
        merged = {
            key: _full_identifier(value)
            for key, value in textures.items()
            if isinstance(value, str) and _full_identifier(value) in moved
        }
        if not merged:
            continue

        chain = _elements_chain(models, data)
        if chain is None:
            print(f"        WARNING!!! {identifier} uses an objmc bake but has no carriers", flush=True)
            continue
        if len(chain) > 1:
            data = _inline(chain)
            inlined.update(_full_identifier(m["parent"]) for m in chain[:-1] if "parent" in m)
        else:
            data = copy.deepcopy(data)

        for element in data["elements"]:
            for face in element.get("faces", {}).values():
                texture = face.get("texture", "")
                if not texture.startswith("#") or texture[1:] not in merged or "uv" not in face:
                    continue
                bake = bakes[merged[texture[1:]]]
                _, row, height = moved[bake.identifier]
                uv = face["uv"]
                face["uv"] = [
                    uv[0],
                    float(f"{(row + uv[1] * bake.height / 16) * 16 / height:.6g}"),
                    uv[2],
                    float(f"{(row + uv[3] * bake.height / 16) * 16 / height:.6g}"),
                ]
        for key, value in merged.items():
            data["textures"][key] = moved[value][0]
        util.printDebug(f"    Moved the carriers of {identifier} to a merged bake", debug)
        _write_model(file, data, compress)
    return inlined


def _elements_chain(models: dict, data: dict):
    """The model and the parents it inherits from, up to the first with
    elements; None if none has any."""
    chain, seen = [data], set()
    while "elements" not in chain[-1]:
        parent = chain[-1].get("parent")
        if not parent or _full_identifier(parent) in seen or _full_identifier(parent) not in models:
            return None
        seen.add(_full_identifier(parent))
        chain.append(models[_full_identifier(parent)][1])
    return chain


def _inline(chain: list) -> dict:
    """The model with what it inherits up to its elements folded into it, the
    way the client resolves a parent: the child's keys win, textures merge."""
    data = copy.deepcopy(chain[-1])
    textures = dict(data.get("textures") or {})
    for model in reversed(chain[:-1]):
        textures.update(model.get("textures") or {})
        data.update({k: copy.deepcopy(v) for k, v in model.items() if k not in ("parent", "textures")})
    if "parent" in chain[-1]:
        data["parent"] = chain[-1]["parent"]
    else:
        data.pop("parent", None)
    data["textures"] = textures
    return data


# --------------------------------------------------------------------------
# Removing what nothing uses
# --------------------------------------------------------------------------


def _remove_unused(output_path: Path, bakes: dict, moved: dict, inlined: set):
    models = _read_models(output_path)
    textures_used, parents_used = set(), set()
    for _, data in models.values():
        for value in (data.get("textures") or {}).values():
            if isinstance(value, str) and not value.startswith("#"):
                textures_used.add(_full_identifier(value))
        if isinstance(data.get("parent"), str):
            parents_used.add(_full_identifier(data["parent"]))

    sprites = {sprite for sprite, _, _ in moved.values()}
    for identifier in moved:
        if identifier not in sprites and identifier not in textures_used:
            bakes[identifier].path.unlink()
    for identifier in inlined:
        if identifier not in parents_used and identifier in models:
            models[identifier][0].unlink()
