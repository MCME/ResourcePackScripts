"""Crop a pack's vegetation planes to their textures' visible texels.

    python cropPlanes.py <pack> [--parent block/3x3x3vegetation] [--margin 4] [--check]

The 3x3x3 vegetation models (short grass and the like) are eight planes of
3x3 blocks each, but their textures are mostly empty: about 16% of the area
has a visible texel. Every empty texel is still drawn - rasterised, run
through the whole terrain shader and only then discarded - so a meadow costs
several times what it shows.

Each such parent's planes are shrunk, in the parent itself, to the rectangle
that has visible texels in any of the textures its models give that plane,
and their UVs recomputed so every texel lands where it did: the same picture,
fewer fragments, and the models untouched. A plane that no model's texture
shows is dropped. --margin keeps that many texels around the visible ones,
aligned to as many, so a mipmap level or a supersampled pixel at the edge
still sees the transparency it saw before.

A run crops what the parent has, so a second run changes nothing. When a
texture grows past its plane's crop, restore the parent's full planes (from
git) before running again. --check changes nothing and fails when a parent's
planes aren't the ones a run would write.
"""

import argparse
import json
import math
import sys
from pathlib import Path

from PIL import Image

# Texture-space direction of u along each face: +1 when u1 is at the plane's
# lower coordinate, as the game maps a face's uv onto it; v1 is always at the top
U_AT_FROM = {"south": True, "west": True, "north": False, "east": False}
# The in-plane horizontal axis of each face (0 x, 2 z)
FACE_AXIS = {"north": 0, "south": 0, "east": 2, "west": 2}
DECIMALS = 4


def model_path(pack, reference):
    namespace, _, path = reference.partition(":") if ":" in reference else ("minecraft", "", reference)
    return Path(pack) / "assets" / namespace / "models" / (path + ".json")


def texture_path(pack, reference):
    namespace, _, path = reference.partition(":") if ":" in reference else ("minecraft", "", reference)
    return Path(pack) / "assets" / namespace / "textures" / (path + ".png")


def plain(reference):
    return reference.split(":", 1)[1] if reference.startswith("minecraft:") else reference


def resolve_texture(textures, name):
    seen = set()
    while name.startswith("#") and name not in seen:
        seen.add(name)
        name = textures.get(name[1:], name)
    return None if name.startswith("#") else name


class Alpha:
    """Visible texels of the pack's textures, by reference."""

    def __init__(self, pack):
        self.pack = pack
        self.cache = {}

    def get(self, reference):
        if reference not in self.cache:
            path = texture_path(self.pack, reference)
            if not path.exists():
                self.cache[reference] = None
            else:
                with Image.open(path) as image:
                    alpha = image.convert("RGBA").getchannel("A")
                    self.cache[reference] = (alpha.size, alpha.point(lambda a: 255 if a else 0).getbbox())
        return self.cache[reference]


def pixel_range(low, high, margin, size):
    """The texel rectangle edge, widened by the margin and aligned to it."""
    if margin:
        low = (low - margin) // margin * margin
        high = -(-(high + margin) // margin) * margin
    return max(low, 0), min(high, size)


def crop_element(element, texture_sets, alpha, margin):
    """The element cropped to the texels any of the texture sets shows on it; None when none shows anything; the element itself when it can't tell."""
    start, end = element.get("from"), element.get("to")
    flat = [i for i in range(3) if start[i] == end[i]]
    faces = element.get("faces", {})
    if len(flat) != 1 or flat[0] == 1 or not faces:
        return element
    axis = 2 - flat[0]  # a plane flat on z spans x, and the other way round
    ranges = []  # (axis low, axis high, y low, y high) each face needs
    for direction, face in faces.items():
        uv = face.get("uv")
        if FACE_AXIS.get(direction) != axis or uv is None or face.get("rotation", 0) % 360:
            return element
        for textures in texture_sets:
            texture = resolve_texture(textures, face.get("texture", ""))
            info = alpha.get(texture) if texture else None
            if info is None:
                return element
            (width, height), box = info
            if height != width:
                return element  # an animation strip: each frame would need its own box
            if box is None:
                continue
            u1, v1, u2, v2 = uv
            x0, x1 = pixel_range(box[0], box[2], margin, width)
            y0, y1 = pixel_range(box[1], box[3], margin, height)
            # texel edges in uv, then where the face puts them
            ua, ub = sorted((x0 * 16 / width, x1 * 16 / width))
            va, vb = y0 * 16 / height, y1 * 16 / height
            ua, ub = max(ua, min(u1, u2)), min(ub, max(u1, u2))
            va, vb = max(va, min(v1, v2)), min(vb, max(v1, v2))
            if ua >= ub or va >= vb:
                continue
            a_lo, a_hi = start[axis], end[axis]
            if not U_AT_FROM[direction]:
                a_lo, a_hi = a_hi, a_lo
            to_a = lambda u: a_lo + (u - u1) * (a_hi - a_lo) / (u2 - u1)
            to_y = lambda v: end[1] + (v - v1) * (start[1] - end[1]) / (v2 - v1)
            ranges.append((*sorted((to_a(ua), to_a(ub))), *sorted((to_y(va), to_y(vb)))))
    if not ranges:
        return None
    lo_a = math.floor(min(r[0] for r in ranges) * 10**DECIMALS) / 10**DECIMALS
    hi_a = math.ceil(max(r[1] for r in ranges) * 10**DECIMALS) / 10**DECIMALS
    lo_y = math.floor(min(r[2] for r in ranges) * 10**DECIMALS) / 10**DECIMALS
    hi_y = math.ceil(max(r[3] for r in ranges) * 10**DECIMALS) / 10**DECIMALS
    lo_a, hi_a = max(lo_a, min(start[axis], end[axis])), min(hi_a, max(start[axis], end[axis]))
    lo_y, hi_y = max(lo_y, start[1]), min(hi_y, end[1])

    cropped = dict(element)
    cropped["from"], cropped["to"] = list(start), list(end)
    cropped["from"][axis], cropped["to"][axis] = number(lo_a), number(hi_a)
    cropped["from"][1], cropped["to"][1] = number(lo_y), number(hi_y)
    cropped["faces"] = {}
    for direction, face in faces.items():
        u1, v1, u2, v2 = face["uv"]
        a_lo, a_hi = start[axis], end[axis]
        new_lo, new_hi = lo_a, hi_a
        if not U_AT_FROM[direction]:
            a_lo, a_hi, new_lo, new_hi = a_hi, a_lo, hi_a, lo_a
        to_u = lambda a: u1 + (a - a_lo) * (u2 - u1) / (a_hi - a_lo)
        to_v = lambda y: v1 + (end[1] - y) * (v2 - v1) / (end[1] - start[1])
        cropped["faces"][direction] = dict(
            face, uv=[number(to_u(new_lo)), number(to_v(hi_y)), number(to_u(new_hi)), number(to_v(lo_y))]
        )
    return cropped


def number(value):
    value = round(value, DECIMALS)
    return int(value) if value == int(value) else value


def load(path):
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def plane_parent(pack, model, prefix):
    """The path of the model's nearest ancestor named prefix* that has elements, and the textures down the chain."""
    if model.get("elements"):
        return None, None  # its own elements replace the parent's
    textures = {}
    chain = [model]
    current = model
    while True:
        parent = current.get("parent")
        if not isinstance(parent, str):
            return None, None
        path = model_path(pack, parent)
        if not path.exists():
            return None, None
        current = load(path)
        chain.append(current)
        if plain(parent).startswith(prefix) and current.get("elements"):
            break
    for link in reversed(chain):
        textures.update(link.get("textures", {}))
    return path, textures


def dump(value, indent, depth=0):
    """JSON as Blockbench writes it: arrays of numbers, faces and rotations on one line."""
    flat = lambda v: not isinstance(v, (dict, list)) or (isinstance(v, list) and not any(isinstance(x, (dict, list)) for x in v))
    if flat(value) or (isinstance(value, dict) and depth >= 3 and all(flat(v) for v in value.values())):
        return json.dumps(value, ensure_ascii=False)
    pad, inner = indent * depth, indent * (depth + 1)
    if isinstance(value, list):
        items = [inner + dump(v, indent, depth + 1) for v in value]
        return "[\n" + ",\n".join(items) + "\n" + pad + "]"
    items = [inner + json.dumps(k) + ": " + dump(v, indent, depth + 1) for k, v in value.items()]
    return "{\n" + ",\n".join(items) + "\n" + pad + "}"


def write_like(path, model):
    """Writes the model in the indent, line endings and final newline the file already has."""
    text = path.read_bytes().decode("utf-8-sig")
    newline = "\r\n" if "\r\n" in text else "\n"
    second = text.replace("\r\n", "\n").split("\n")[1:2]
    indent = second[0][: len(second[0]) - len(second[0].lstrip())] if second else "\t"
    end = "\n" if text.endswith("\n") else ""
    path.write_text(dump(model, indent or "\t") + end, encoding="utf-8", newline=newline)


def crop_pack(pack, prefix, margin, write):
    """{parent path: (models, planes before, planes after, area kept)} for every parent it would change."""
    alpha = Alpha(pack)
    users = {}  # parent path: the texture sets of the models under it
    for path in sorted(Path(pack).glob("assets/*/models/**/*.json")):
        parent, textures = plane_parent(pack, load(path), prefix)
        if parent is not None:
            users.setdefault(parent, []).append(textures)
    changed = {}
    for path, texture_sets in users.items():
        parent = load(path)
        elements = []
        before = after = 0.0
        for element in parent["elements"]:
            cropped = crop_element(element, texture_sets, alpha, margin)
            before += area(element)
            if cropped is not None:
                elements.append(cropped)
                after += area(cropped)
        if parent["elements"] == elements:
            continue
        changed[path] = (len(texture_sets), len(parent["elements"]), len(elements), after / before if before else 1.0)
        if write:
            parent["elements"] = elements
            write_like(path, parent)
    return changed


def area(element):
    sizes = sorted(abs(b - a) for a, b in zip(element["from"], element["to"]))
    return sizes[1] * sizes[2]


def main():
    parser = argparse.ArgumentParser(description="Crop a pack's vegetation planes to their visible texels.")
    parser.add_argument("pack_path", help="The pack, with its assets/ folder.")
    parser.add_argument("--parent", default="block/3x3x3vegetation", help="Crop models under parents named this*.")
    parser.add_argument("--margin", type=int, default=4, help="Texels kept around the visible ones, aligned to as many.")
    parser.add_argument("--check", action="store_true", help="Change nothing; fail when a parent isn't cropped.")
    args = parser.parse_args()

    changed = crop_pack(args.pack_path, args.parent, args.margin, write=not args.check)
    for path, (models, before, after, kept) in changed.items():
        print(f"{path} ({models} models): {before} planes -> {after}, {kept:.0%} of their area")
    if changed:
        print(f"{args.pack_path}: {len(changed)} parent(s) {'not cropped' if args.check else 'cropped'}")
    if args.check and changed:
        sys.exit("ERROR: run cropPlanes.py on the pack")


if __name__ == "__main__":
    main()
