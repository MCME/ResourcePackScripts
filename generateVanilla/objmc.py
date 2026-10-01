"""
objmc_remastered.py

Standalone Python port of the vertex/uv/position encoding logic introduced by
the objcubed.js Blockbench plugin (a rewrite of the original objmc.py by
Godlander). This script is scoped to STATIC BLOCK-TYPE models only:

    - single .obj frame, single texture, no animation
    - no color-behavior tinting, no autorotate, no GUI/display transforms
      (those only affect item/entity rendering, not blocks)

It keeps the CLI/structure of the original objmc.py as closely as possible
while writing the newer 2-row header + block-centered element format that the
shaders in this pack (assets/minecraft/shaders/include/objmc_main.glsl) expect.

Github (original): https://github.com/Godlander/objmc
"""

import sys
import os
import math
import json
import argparse

from PIL import Image


# --------------------------------
# INPUT (defaults, all overridable via CLI args or objmc() kwargs)
# --------------------------------

obj = ""
tex = ""

# Output json & png
output = ["block.json", "block/out.png"]

# Position & Scaling
# just adds & multiplies vertex positions before encoding, so you don't have
# to re-export the model
offset = (0.0, 0.0, 0.0)
scale = 1.0

# Flip uv
# if your model renders but textures are not right try toggling this
flipuv = False

# No Shadow
# disable face normal shading (lightmap color still applies)
noshadow = False

# Visibility
# 3 bits for: world, hand, gui (blocks only ever care about the "world" bit)
visibility = 7

# No power of two textures
# saves a bit of space, but makes it not optifine compatible
nopow = True

# Mipmap levels
# how many mip levels the shader may sample the texture at. The atlas mipmaps
# the whole output image, data rows included, so the texture is aligned to
# 2^mipmap rows and padded with copies of its edge rows to keep the data from
# bleeding into it. 0 keeps the unpadded layout, sampled at full size only.
# Matches OBJMC_MIPMAP_LEVELS in constants.py, which the generator passes.
mipmap = 4
MAX_MIPMAP = 4


class col:
    head = "\033[95m"
    blue = "\033[94m"
    cyan = "\033[96m"
    green = "\033[92m"
    warn = "\033[93mWarning: "
    err = "\033[91mError: "
    end = "\033[0m"
    bold = "\033[1m"
    underline = "\033[4m"


class ObjmcError(Exception):
    pass


# --------------------------------
# obj parsing / vertex indexing
# --------------------------------

def readobj(name, nfaces=0):
    d = {"positions": [], "uvs": [], "faces": []}
    with open(name, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line[0] == "#":
                continue
            parts = line.split()
            if parts[0] == "v":
                d["positions"].append([float(parts[1]), float(parts[2]), float(parts[3])])
            elif parts[0] == "vt":
                d["uvs"].append([float(parts[1]), float(parts[2])])
            elif parts[0] == "f":
                face = []
                for p in parts[1:]:
                    refs = p.split("/")
                    pidx = int(refs[0]) - 1 if refs[0] else 0
                    uidx = int(refs[1]) - 1 if len(refs) > 1 and refs[1] else 0
                    face.append((pidx, uidx))
                d["faces"].append(face)
    if nfaces > 0 and len(d["faces"]) != nfaces:
        raise ObjmcError(f"mismatched obj face count: expected {nfaces}, got {len(d['faces'])}")
    return d


# index vertices: dedupe identical position/uv pairs into shared indices
def build_vertex_data(o):
    count = [0, 0]
    mem = {"positions": {}, "uvs": {}}
    data = {"positions": [], "uvs": [], "vertices": []}

    def index_vert(vert):
        pos = o["positions"][vert[0]] if vert[0] < len(o["positions"]) else [0.0, 0.0, 0.0]
        uv = o["uvs"][vert[1]] if vert[1] < len(o["uvs"]) else [0.0, 0.0]
        posh = ",".join(str(c) for c in pos)
        uvh = f"{uv[0]:.8f},{uv[1]:.8f}"
        pi = mem["positions"].get(posh)
        if pi is None:
            pi = count[0]
            count[0] += 1
            mem["positions"][posh] = pi
            data["positions"].append(pos)
        ui = mem["uvs"].get(uvh)
        if ui is None:
            ui = count[1]
            count[1] += 1
            mem["uvs"][uvh] = ui
            data["uvs"].append(uv)
        data["vertices"].append([pi, ui])

    for face in o["faces"]:
        n = min(4, len(face))
        for i in range(n):
            index_vert(face[i])
        # Pad a triangle to a quad by repeating the LAST vertex (v0,v1,v2,v2):
        # the 2nd sub-triangle (v0,v2,v2) is then zero-area/degenerate. Repeating
        # the MIDDLE vertex instead gives a reverse-wound coincident face that
        # flickers / z-fights.
        if len(face) == 3:
            index_vert(face[2])
        if len(face) > 4:
            print(col.warn + "Found N-Gon" + col.end)

    return data


# --------------------------------
# pixel encoding
# --------------------------------

def u24(v):
    return [math.trunc(v / 65536) & 255, math.trunc(v / 256) & 255, math.trunc(v) & 255]


def pos_pixels(pos, scale, off):
    out = []
    for i in range(3):
        v = 8388608 + pos[i] * 65536 * scale + off[i] * 65536
        out.append(u24(v) + [255])
    return out


def uv_pixels(uv):
    # Clamp to [0,1]: the shader samples within one frame, so a UV outside the
    # unit square (tiling / negative) would otherwise wrap or read garbage.
    out = []
    for v in uv:
        c = max(0.0, min(1.0, v)) * 65535
        out.append(u24(c) + [255])
    return out


def vert_pixels(vert):
    poi, uvi = vert
    return [u24(poi) + [255], u24(uvi) + [255]]


# --------------------------------
# texture layout
# --------------------------------

def texture_layout(start, th, mipmap):
    """(first texture row, first data row) for a texture of th rows that may
    begin at row `start`. Must match the shader's objmc_main.glsl.

    With mipmapping, a mip level n texel covers an aligned 2^n x 2^n block of
    the image, so the texture starts on a 2^mipmap row boundary with at least
    one block of padding above, and the data starts one full block after the
    block holding the texture's last row. Every block a mip level up to
    `mipmap` samples the texture from then holds only texture and padding.
    """
    if mipmap <= 0:
        return start, start + th
    block = 1 << mipmap
    top = -(-(start + block) // block) * block
    return top, -(-(top + th) // block) * block + block


# --------------------------------
# carrier element orientation
# --------------------------------

# Carrier elements are shrunk to this fraction of the real OBJ geometry and
# recentered on the block, so the placeholder shape never clips into
# neighbouring blocks regardless of how large the source model is.
ELEMENT_SCALE = 0.3
BLOCK_CENTER = 8.0


def model_center(positions):
    xs = [p[0] for p in positions]
    ys = [p[1] for p in positions]
    zs = [p[2] for p in positions]
    return ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, (min(zs) + max(zs)) / 2)


DIRECTION_AXIS = {"east": ("x", 1), "west": ("x", -1), "up": ("y", 1),
                  "down": ("y", -1), "south": ("z", 1), "north": ("z", -1)}


def free_rotation(direction, normal):
    """Exact 3-axis element rotation (Minecraft 25w46a+ / 1.21.11 block model
    format: per-element "x"/"y"/"z" degrees, unrestricted angle, applied in
    that order - model is rotated around X, then Y, then Z). Solves for the
    (x, y, z) that carries the base cardinal plane's normal exactly onto the
    real face normal, fixing one redundant "twist" DOF (the in-plane spin,
    which doesn't affect facing direction) to 0."""
    axis_p, sign_p = DIRECTION_AXIS[direction]
    # Normal expressed with the base axis' own sign so its dominant component is positive.
    px, py, pz = sign_p * normal[0], sign_p * normal[1], sign_p * normal[2]

    if axis_p == "x":
        # x fixed at 0 (X is rotated first, so it's invariant to its own angle).
        cz = math.sqrt(max(0.0, 1.0 - pz * pz))
        x, y, z = 0.0, math.degrees(math.atan2(-pz, cz)), math.degrees(math.atan2(py, px))
    elif axis_p == "y":
        # z fixed at 0.
        sx = math.sqrt(max(0.0, 1.0 - py * py))
        x = math.degrees(math.atan2(sx, py))
        y = 0.0 if sx < 1e-9 else math.degrees(math.atan2(px, pz))
        z = 0.0
    else:
        # z fixed at 0.
        cx = math.sqrt(max(0.0, 1.0 - py * py))
        x = math.degrees(math.atan2(-py, cx))
        y = 0.0 if cx < 1e-9 else math.degrees(math.atan2(px, pz))
        z = 0.0

    if abs(x) < 1e-6 and abs(y) < 1e-6 and abs(z) < 1e-6:
        return None
    return {"origin": [8, 8, 8], "x": x, "y": y, "z": z}


def rotation_matrix(rotation):
    # Matches Minecraft's element rotation order: rotate X, then Y, then Z (M = Rz*Ry*Rx).
    x, y, z = (math.radians(rotation[k]) for k in ("x", "y", "z"))
    cx, sx, cy, sy, cz, sz = math.cos(x), math.sin(x), math.cos(y), math.sin(y), math.cos(z), math.sin(z)
    return (
        (cz * cy, cz * sy * sx - sz * cx, cz * sy * cx + sz * sx),
        (sz * cy, sz * sy * sx + cz * cx, sz * sy * cx - cz * sx),
        (-sy, cy * sx, cy * cx),
    )


def carrier_bounds(face_positions, center, rotation):
    origin = (BLOCK_CENTER, BLOCK_CENTER, BLOCK_CENTER)
    pts = [
        [(p[a] - center[a]) * ELEMENT_SCALE + origin[a] for a in range(3)]
        for p in face_positions
    ]
    if rotation is not None:
        m = rotation_matrix(rotation)
        local = []
        for p in pts:
            rel = [p[a] - origin[a] for a in range(3)]
            # M is orthogonal, so its transpose undoes the rotation Minecraft will re-apply.
            unrot = [sum(m[j][a] * rel[j] for j in range(3)) for a in range(3)]
            local.append([unrot[a] + origin[a] for a in range(3)])
        pts = local
    elem_from = [min(p[a] for p in pts) for a in range(3)]
    elem_to = [max(p[a] for p in pts) for a in range(3)]
    return elem_from, elem_to


def face_normal(positions):
    # Newell's method: robust for faces with >3 verts / near-collinear triples.
    nx = ny = nz = 0.0
    n = len(positions)
    for i in range(n):
        x1, y1, z1 = positions[i]
        x2, y2, z2 = positions[(i + 1) % n]
        nx += (y1 - y2) * (z1 + z2)
        ny += (z1 - z2) * (x1 + x2)
        nz += (x1 - x2) * (y1 + y2)
    length = math.sqrt(nx * nx + ny * ny + nz * nz)
    if length < 1e-12:
        return (0.0, 0.0, -1.0)  # degenerate face: default to north
    return (nx / length, ny / length, nz / length)


def classify_direction(normal):
    # OBJ axes map 1:1 onto Minecraft block-space axes (+Y up, -Z north).
    nx, ny, nz = normal
    ax, ay, az = abs(nx), abs(ny), abs(nz)
    if ay >= ax and ay >= az:
        return "up" if ny > 0 else "down"
    if ax >= ay and ax >= az:
        return "east" if nx > 0 else "west"
    return "south" if nz > 0 else "north"


# --------------------------------
# main export
# --------------------------------

def objmc(obj, tex, output, scale=1.0, offset=(0.0, 0.0, 0.0), visibility=7,
          flipuv=False, noshadow=False, nopow=True, mipmap=4):
    """Convert a single .obj + texture into a custom-model .json + .png pair
    using the objcubed encoding, for a static block-type model."""

    output = list(output)
    if output[0][-5:] != ".json":
        output[0] += ".json"
    if output[1][-4:] != ".png":
        output[1] += ".png"
    for path in output:
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)

    print("\n" + col.cyan + "objmc start" + col.end)

    o = readobj(obj)
    data = build_vertex_data(o)
    nfaces = len(o["faces"])
    if nfaces == 0:
        raise ObjmcError("No faces found in OBJ")
    nvertices = nfaces * 4

    im = Image.open(tex).convert("RGBA")
    tw, th = im.size
    if tw < 8:
        raise ObjmcError("minimum texture size is 8px wide")
    if tw > 65535 or th > 65535:
        raise ObjmcError(f"texture too large: {tw}x{th} (max 65535)")
    if not 0 <= mipmap <= MAX_MIPMAP:
        raise ObjmcError(f"mipmap must be 0 to {MAX_MIPMAP}, got {mipmap}")

    BYTE24_MAX = 16777215
    if len(data["positions"]) > BYTE24_MAX:
        raise ObjmcError(f"too many unique positions ({len(data['positions'])} > {BYTE24_MAX})")
    if len(data["uvs"]) > BYTE24_MAX:
        raise ObjmcError(f"too many unique UVs ({len(data['uvs'])} > {BYTE24_MAX})")

    # Position codec: byte24 = 8388608 + v_world*65536, decodable only in [-128, +128).
    bake_offset = [offset[0], offset[1] - 0.5, offset[2]]
    for pos in data["positions"]:
        for a in range(3):
            w = pos[a] * scale + bake_offset[a]
            if w < -128 or w >= 128:
                raise ObjmcError(
                    f"model out of range: a vertex reaches {w:.2f} on axis {'XYZ'[a]}; "
                    "must stay within [-128, 128) after scale+offset. Lower Scale or shrink the model."
                )

    headerrows = 2
    uvh = math.ceil(nfaces / tw)
    textop, datatop = texture_layout(headerrows + uvh, th, mipmap)
    vph = math.ceil(len(data["positions"]) * 3 / tw)
    vth = math.ceil(len(data["uvs"]) * 2 / tw)
    vh = math.ceil(len(data["vertices"]) * 2 / tw)

    if vph > 65535 or vth > 65535:
        raise ObjmcError(f"encoded data section too tall (positions {vph}, uvs {vth} rows; max 65535)")

    ty = datatop + vph + vth + vh
    if not nopow:
        ty = 1 << (ty - 1).bit_length()
    if (ty > 4096 and tw < 4096) or (ty > 8 * tw):
        print(
            col.warn
            + "output height may be too high, consider increasing width of input "
            + "texture or reducing number of frames to bring the output texture "
            + "closer to a square."
            + col.end
        )

    print(f"faces: {nfaces}, verts: {nvertices}, tex: {(tw, th)}, flipuv: {flipuv}")
    print(f"uvh: {uvh}, vph: {vph}, vth: {vth}, vh: {vh}, total: {ty}")
    print(f"offset: {offset}, scale: {scale}, noshadow: {noshadow}, mipmap: {mipmap}")
    print(
        "visible:"
        + (" world" if visibility & 4 > 0 else "")
        + (" hand" if visibility & 2 > 0 else "")
        + (" gui" if visibility & 1 > 0 else "")
    )
    print("Creating files...")

    out = Image.new("RGBA", (tw, int(ty)), (0, 0, 0, 0))
    px = out.load()

    def put(x, y, r, g, b, a=255):
        if x < 0 or x >= tw or y < 0 or y >= ty:
            return
        px[x, y] = (r & 255, g & 255, b & 255, a & 255)

    # --- Row 0: header ---
    # marker
    put(0, 0, 12, 34, 56, 255)
    # texsize: width, height(frame) high byte (low byte lives at t[7].r)
    put(1, 0, tw // 256, tw % 256, th // 256, 255)
    # nvertices (top 3 bytes; low byte lives at t[7].g)
    put(2, 0, (nvertices // 16777216) % 256, (nvertices // 65536) % 256, (nvertices // 256) % 256, 255)
    # nframes (=1), ntextures (=1) — no animation support in this script
    put(3, 0, 0, 0, 1, 1)
    # duration(=1)/autoplay(0)/easing(0)/interpolation(0) — inert, no animation
    put(4, 0, 0, 0, 1, 128)
    # data heights: vph, vth high byte (low byte lives at t[7].b)
    put(5, 0, (vph // 256) % 256, vph % 256, (vth // 256) % 256, 255)
    # noshadow + visibility; mipmap levels the texture is padded for
    put(6, 0, (int(noshadow) << 7) | (visibility << 2), mipmap, 0, 255)
    # low bytes: frameH, nvertices, vth
    put(7, 0, th % 256, nvertices % 256, vth % 256, 255)
    # t[8..15]: GUI q16 transform — unused for block models, left zeroed
    for x in range(8, 16):
        put(x, 0, 0, 0, 0, 255)
    # Row 1: texture-animation clock / dynamic slot markers — unused, zeroed
    for x in range(0, tw):
        put(x, 1, 0, 0, 0, 255)

    # --- texture data (single, non-animated) ---
    tex_px = im.load()
    for py in range(th):
        srcy = py if flipuv else (th - 1 - py)
        dsty = textop + py
        for x in range(tw):
            r, g, b, a = tex_px[x, srcy]
            put(x, dsty, r, g, b, a)
    # mipmap padding: repeat the texture's edge rows out to the data either side
    for dsty in range(headerrows + uvh, textop):
        for x in range(tw):
            px[x, dsty] = px[x, textop]
    for dsty in range(textop + th, datatop):
        for x in range(tw):
            px[x, dsty] = px[x, textop + th - 1]

    # --- json model elements + uv header ---
    js = {
        "textures": {"0": os.path.splitext(output[1])[0]},
        "elements": [],
    }
    center = model_center(o["positions"])
    for i, face in enumerate(o["faces"]):
        posx = i % tw
        posy = i // tw + headerrows
        put(posx, posy, (posx // 256) % 256, posx % 256, (posy // 256) % 256, posy % 256)

        # Carrier geometry = the real face, shrunk and recentered on the block
        # so it never clips into neighbouring blocks; the element is then
        # rotated (exact x/y/z, Minecraft 25w46a+) to match the true face
        # normal, so vanilla per-face diffuse shading lines up correctly.
        face_positions = [o["positions"][v[0]] for v in face]
        normal = face_normal(face_positions)
        direction = classify_direction(normal)
        rotation = free_rotation(direction, normal)
        elem_from, elem_to = carrier_bounds(face_positions, center, rotation)

        element = {
            "from": elem_from,
            "to": elem_to,
            "faces": {
                direction: {
                    "uv": [
                        (posx + 0.1) * 16 / tw,
                        (posy + 0.1) * 16 / ty,
                        (posx + 0.9) * 16 / tw,
                        (posy + 0.9) * 16 / ty,
                    ],
                    "texture": "#0",
                    "tintindex": 0,
                }
            },
        }
        if rotation is not None:
            element["rotation"] = rotation
        js["elements"].append(element)

    print("Writing json model...")
    with open(output[0], "w") as model:
        model.write(json.dumps(js, separators=(",", ":")))

    # --- position data ---
    print("Writing position data...")
    y = datatop
    uv_clamped = False
    for i, pos in enumerate(data["positions"]):
        for j, pix in enumerate(pos_pixels(pos, scale, bake_offset)):
            p = i * 3 + j
            put(p % tw, y + p // tw, *pix)

    # --- uv data ---
    print("Writing uv data...")
    y = datatop + vph
    for i, uv in enumerate(data["uvs"]):
        if uv[0] < -1e-6 or uv[0] > 1 + 1e-6 or uv[1] < -1e-6 or uv[1] > 1 + 1e-6:
            uv_clamped = True
        for j, pix in enumerate(uv_pixels(uv)):
            p = i * 2 + j
            put(p % tw, y + p // tw, *pix)
    if uv_clamped:
        print(col.warn + "some UVs fall outside the 0..1 frame (tiling/negative) and "
              "were clamped — those faces may look wrong." + col.end)

    # --- vertex data ---
    print("Writing vertex data...")
    y = datatop + vph + vth
    for i, vert in enumerate(data["vertices"]):
        for j, pix in enumerate(vert_pixels(vert)):
            p = i * 2 + j
            put(p % tw, y + p // tw, *pix)

    print("Saving files...")
    out.save(output[1])
    print(col.green + "Complete" + col.end)


# --------------------------------
# argument parsing
# --------------------------------

class ArgumentParserError(Exception):
    pass


class ThrowingArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise ArgumentParserError(message)


def build_parser():
    parser = ThrowingArgumentParser(
        description=(
            "python script to convert a static .OBJ block model into Minecraft, "
            "rendering it in game with a core shader.\n"
            "Github: https://github.com/Godlander/objmc"
        )
    )
    parser.add_argument("--obj", type=str, help="Object file", default=obj)
    parser.add_argument("--tex", type=str, help="Texture file", default=tex)
    parser.add_argument("--out", type=str, help="Output json and png", nargs=2, default=output)
    parser.add_argument("--offset", type=float, help="Positional offset of model", nargs=3, default=offset)
    parser.add_argument("--scale", type=float, help="Scale of model", default=scale)
    parser.add_argument("--visibility", type=int, help="Determines where the model is visible", default=visibility)
    parser.add_argument("--flipuv", action="store_true", dest="flipuv", help="Invert the texture to compensate for flipped UV")
    parser.add_argument("--noshadow", action="store_true", dest="noshadow", help="Disable shadows from face normals")
    parser.add_argument("--nopow", action="store_true", dest="nopow", help="Disable power of two textures")
    parser.add_argument("--mipmap", type=int, help=f"Mipmap levels to pad the texture for, 0 to {MAX_MIPMAP}", default=mipmap)
    return parser


def main(argv=None):
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except ArgumentParserError as e:
        print(col.err + "Invalid arguments: " + col.end + str(e))
        sys.exit(1)

    try:
        objmc(
            args.obj,
            args.tex,
            list(args.out),
            scale=args.scale,
            offset=tuple(args.offset),
            visibility=args.visibility,
            flipuv=args.flipuv,
            noshadow=args.noshadow,
            nopow=args.nopow,
            mipmap=args.mipmap,
        )
    except ObjmcError as e:
        print(col.err + str(e) + col.end)
        sys.exit(1)


if __name__ == "__main__":
    main()
