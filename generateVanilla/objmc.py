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


# A face pointer's alpha. Below 255, so the client puts every objmc face in its
# translucent layer, which the shader's soft edges need; high, because OptiFine
# makes nearly transparent pixels fully transparent - and the client recolours
# fully transparent ones - which once wiped pointers holding a row in alpha.
# Every other pixel the shader reads is opaque.
POINTER_ALPHA = 254
# A pointer's column and row are 12 bits each.
POINTER_MAX = 4096


def pointer_pixel(x, y):
    """A face pointer: its own column and row in the bake, 12 bits each, in
    red, green and blue - objmc_main.glsl subtracts them from the pixel's
    atlas position to find the bake's header."""
    return x >> 4, ((x & 15) << 4) | (y >> 8), y & 255, POINTER_ALPHA


def has_translucent_texels(image):
    """Whether any texel is partly transparent (alpha strictly between 0 and 255).

    Every objmc face renders in the client's translucent layer: its UVs cover
    only its pointer pixel, whose alpha is POINTER_ALPHA. Mipmapped and
    filtered sampling blurs a cutout texture's edges into a band of partly
    transparent pixels there, which the layer blends and still writes to
    depth - showing through to whatever was drawn before them. So the shader
    sharpens such a texture's edges to about a pixel; one with partly
    transparent texels of its own is left as it is.
    """
    lo, hi = image.getchannel("A").getextrema()
    if lo == 255 or hi == 0:
        return False
    return any(0 < a < 255 for a in image.getchannel("A").getdata())


def transparent_zeroed(image):
    """The image with every fully transparent texel as (0, 0, 0, 0)."""
    zeroed = Image.new("RGBA", image.size)
    zeroed.putdata([p if p[3] > 0 else (0, 0, 0, 0) for p in image.getdata()])
    return zeroed


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

# A carrier element sits where its real face sits in the block, because the
# client works out ambient occlusion and smooth light for each corner of a
# carrier face at that corner: the real face then gets the occlusion of where
# it is. Positions here are block model units, 0-16 across the block.
#
# Vertices outside the block are clamped to CARRIER_INSET inside it. The
# client's corner blend is not clamped, and extrapolates for a face reaching
# past the block (too dark or too bright); and objmc_main.glsl finds the block
# from floor(Position), so no carrier corner may reach a block boundary.
CARRIER_INSET = 0.5
# Carrier corners stay at least this far inside the block once rotated.
CARRIER_MARGIN = 0.25
# Smallest width of a carrier face, so a sliver of a face still has an area.
CARRIER_MIN_SIZE = 0.05
# Tilt, in degrees, given to a carrier that would face exactly along an axis.
# The client treats such a face in a block with a full collision box (leaves)
# as the block's outside face, lit by the block in front of it - black when
# that block is solid. Any tilt at all stops that.
CARRIER_TILT = 0.1
# Directions whose carriers are left flat instead - along the axis, unrotated -
# so that the client does treat them as the block's outside face, occluded and
# lit by the layer in front. For an upward face that is what lies above it: the
# open air over a canopy. A rotated face is occluded by its own block's layer
# instead, which for an upward face in a canopy is the leaves beside it - dark
# from above. A solid block right above an upward face is rare.
CARRIER_FLAT = {"up"}
# Centred carriers (--centred), for a model on a block the client shifts by a
# random offset: every vertex moves, so a carrier near a block face could move
# into the next block, and the shader would place that corner of the real face
# there - stretching it. Centred, each carrier is its face shrunk to this
# fraction about the block's centre, out of any shift's reach; the shader puts
# the real face where the client moved its carrier, keeping the offset. The
# client's occlusion is then the same at every corner of a face.
CENTRED_SCALE = 0.001
BLOCK_CENTER = 8.0

# The corners of an element face in the order the client gives them, as
# (x, y, z) picks between the element's from (0) and to (1). The client
# weighs each corner's occlusion by the same corner of the face's bounds
# (26.2's FaceInfo and BlockModelLighter).
FACE_CORNERS = {
    "down": ((0, 0, 1), (0, 0, 0), (1, 0, 0), (1, 0, 1)),
    "up": ((0, 1, 0), (0, 1, 1), (1, 1, 1), (1, 1, 0)),
    "north": ((1, 1, 0), (1, 0, 0), (0, 0, 0), (0, 1, 0)),
    "south": ((0, 1, 1), (0, 0, 1), (1, 0, 1), (1, 1, 1)),
    "west": ((0, 1, 0), (0, 0, 0), (0, 0, 1), (0, 1, 1)),
    "east": ((1, 1, 1), (1, 0, 1), (1, 0, 0), (1, 1, 0)),
}


def json_number(value, places):
    """value rounded to places decimals, as an int when whole: shorter JSON."""
    value = round(value, places)
    return int(value) if value == int(value) else value


def block_position(pos, scale, offset):
    """Where the shader puts an OBJ vertex in its block, in model units:
    objmc_main.glsl's block origin + 0.5 + pos * scale + the bake offset."""
    return [16 * (pos[a] * scale + offset[a] + (0.0 if a == 1 else 0.5)) for a in range(3)]


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


def tilt_rotation(direction):
    """CARRIER_TILT about an axis across the face, for a face along an axis."""
    across = {"x": "z", "y": "x", "z": "x"}[DIRECTION_AXIS[direction][0]]
    rotation = {"origin": [8, 8, 8], "x": 0.0, "y": 0.0, "z": 0.0}
    rotation[across] = CARRIER_TILT
    return rotation


def rotate(m, p):
    """Rotate a point about the block centre, as the client rotates an element."""
    rel = [p[a] - BLOCK_CENTER for a in range(3)]
    return [sum(m[a][j] * rel[j] for j in range(3)) + BLOCK_CENTER for a in range(3)]


def unrotate(m, p):
    # M is orthogonal, so its transpose undoes the rotation Minecraft will re-apply.
    rel = [p[a] - BLOCK_CENTER for a in range(3)]
    return [sum(m[j][a] * rel[j] for j in range(3)) + BLOCK_CENTER for a in range(3)]


def carrier(face, positions, scale, offset, centred=False):
    """The carrier element for one OBJ face: (direction, rotation or None,
    from, to), and the face's vertices reordered to match it.

    The element is the face's bounds in its own rotated frame - or, for a
    CARRIER_FLAT direction, across the axis - at its place in the block (see
    CARRIER_INSET), or shrunk about the block's centre (CENTRED_SCALE). The
    shader moves carrier corner k onto the
    face's vertex k, and the client occludes corner k as the matching corner of
    the face's bounds (FACE_CORNERS), so the vertices are turned - never
    reversed, which would flip the face - to put each by its corner.
    """
    real = [positions[v[0]] if v[0] < len(positions) else [0.0, 0.0, 0.0] for v in face]
    normal = face_normal(real)
    direction = classify_direction(normal)
    axis = "xyz".index(DIRECTION_AXIS[direction][0])
    if direction in CARRIER_FLAT:
        rotation = None
    else:
        rotation = free_rotation(direction, normal)
        # Below the 0.01 degrees the angles are written to, it would be flat.
        if rotation is None or max(abs(rotation[a]) for a in "xyz") < 0.01:
            rotation = tilt_rotation(direction)
    m = rotation_matrix(rotation or {"x": 0.0, "y": 0.0, "z": 0.0})

    placed = [block_position(p, scale, offset) for p in real]
    if centred:
        middle = [sum(p[a] for p in placed) / len(placed) for a in range(3)]
        pts = [[BLOCK_CENTER + (p[a] - middle[a]) * CENTRED_SCALE for a in range(3)] for p in placed]
    else:
        pts = [[min(max(c, CARRIER_INSET), 16 - CARRIER_INSET) for c in p] for p in placed]
    local = [unrotate(m, p) for p in pts]
    lo = [min(p[a] for p in local) for a in range(3)]
    hi = [max(p[a] for p in local) for a in range(3)]
    if rotation is None:
        lo[axis] = hi[axis] = (lo[axis] + hi[axis]) / 2
    for a in range(3):
        if a != axis and hi[a] - lo[a] < CARRIER_MIN_SIZE:
            mid = (lo[a] + hi[a]) / 2
            lo[a], hi[a] = mid - CARRIER_MIN_SIZE / 2, mid + CARRIER_MIN_SIZE / 2

    # The rotated bounds can reach past the face's own points, so shrink them
    # about the face's centre until every corner is inside the block.
    centre = [sum(p[a] for p in pts) / len(pts) for a in range(3)]
    corners = [rotate(m, [(lo, hi)[pick[a]][a] for a in range(3)]) for pick in FACE_CORNERS[direction]]
    fit = 1.0
    for w in corners:
        for a in range(3):
            d = w[a] - centre[a]
            if d > 0:
                fit = min(fit, (16 - CARRIER_MARGIN - centre[a]) / d)
            elif d < 0:
                fit = min(fit, (CARRIER_MARGIN - centre[a]) / d)
    if fit < 1.0:
        c = unrotate(m, centre)
        lo = [c[a] + (lo[a] - c[a]) * fit for a in range(3)]
        hi = [c[a] + (hi[a] - c[a]) * fit for a in range(3)]
        corners = [rotate(m, [(lo, hi)[pick[a]][a] for a in range(3)]) for pick in FACE_CORNERS[direction]]

    # Where the client takes each corner's occlusion: that corner of the
    # rotated face's bounds, across the face.
    across = [a for a in range(3) if a != axis]
    bmin = [min(w[a] for w in corners) for a in range(3)]
    bmax = [max(w[a] for w in corners) for a in range(3)]
    samples = [[(bmin, bmax)[pick[a]][a] for a in across] for pick in FACE_CORNERS[direction]]

    n = min(4, len(face))
    order = list(face)
    if n >= 3:
        def cost(r):
            turned = [r + k for k in range(n)] + ([r + 2] if n == 3 else [])
            return sum(
                (pts[i % n][a] - s[j]) ** 2
                for i, s in zip(turned, samples)
                for j, a in enumerate(across)
            )
        best = min(range(n), key=cost)
        order = [face[(best + k) % n] for k in range(n)] + list(face[n:])

    return (direction, rotation, lo, hi), order


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
          flipuv=False, noshadow=False, nopow=True, mipmap=4, centred=False):
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
    # Before the vertex data: placing the carriers reorders the faces' vertices.
    carriers = []
    for i, face in enumerate(o["faces"]):
        element, o["faces"][i] = carrier(face, o["positions"], scale, offset, centred)
        carriers.append(element)
    data = build_vertex_data(o)
    nfaces = len(o["faces"])
    if nfaces == 0:
        raise ObjmcError("No faces found in OBJ")
    nvertices = nfaces * 4

    im = Image.open(tex).convert("RGBA")
    tw, th = im.size
    if tw < 8:
        raise ObjmcError("minimum texture size is 8px wide")
    if tw > POINTER_MAX or th > 65535:
        raise ObjmcError(
            f"texture too large: {tw}x{th} (max {POINTER_MAX} wide - a face pointer "
            f"holds its column in 12 bits - and 65535 high)"
        )
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
    if headerrows + uvh > POINTER_MAX:
        raise ObjmcError(
            f"too many faces for a {tw} wide texture ({nfaces}): a face pointer holds "
            f"its row in 12 bits. Use a wider texture."
        )
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
    # nframes (=1), ntextures (=1, written as 255, see POINTER_ALPHA) — no
    # animation support in this script
    put(3, 0, 0, 0, 1, 255)
    # duration(=1)/autoplay/easing/interpolation — inert with one frame, so
    # the alpha is free to be opaque (see POINTER_ALPHA)
    put(4, 0, 0, 0, 1, 255)
    # data heights: vph, vth high byte (low byte lives at t[7].b)
    put(5, 0, (vph // 256) % 256, vph % 256, (vth // 256) % 256, 255)
    # noshadow + visibility; mipmap levels the texture is padded for; whether
    # the texture has partly transparent texels (else the shader sharpens its
    # mipmapped edges, see has_translucent_texels)
    put(6, 0, (int(noshadow) << 7) | (visibility << 2), mipmap,
        int(has_translucent_texels(im)), 255)
    # low bytes: frameH, nvertices, vth
    put(7, 0, th % 256, nvertices % 256, vth % 256, 255)
    # t[8..15]: GUI q16 transform — unused for block models, left zeroed -
    # but for t[9].r, 1 for centred carriers (see CENTRED_SCALE)
    for x in range(8, 16):
        put(x, 0, 0, 0, 0, 255)
    if centred:
        put(9, 0, 1, 0, 0, 255)
    # Row 1: texture-animation clock / dynamic slot markers — unused, zeroed
    for x in range(0, tw):
        put(x, 1, 0, 0, 0, 255)

    # --- texture data (single, non-animated) ---
    # Fully transparent texels are written as (0, 0, 0, 0), which compresses
    # best: their colour is never seen. The client recolours every one of them
    # like its nearest visible texel as it loads the atlas, before mipmapping
    # (26.2's MipmapGenerator -> TextureUtil.solidify).
    tex_px = transparent_zeroed(im).load()
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
    for i, (direction, rotation, elem_from, elem_to) in enumerate(carriers):
        posx = i % tw
        posy = i // tw + headerrows
        put(posx, posy, *pointer_pixel(posx, posy))

        # Carrier geometry = the real face at its place in the block (see
        # carrier), rotated (exact x/y/z, Minecraft 25w46a+) to the true face
        # normal unless left flat (CARRIER_FLAT). Rounded for a smaller file:
        # positions to 0.001 of a pixel, well inside CARRIER_MARGIN; angles to
        # 0.01 degrees, under 0.003 of a pixel at the block's edge; UVs to six
        # figures, far inside the 0.1-0.9 of the pointer pixel they span.
        element = {
            "from": [json_number(c, 3) for c in elem_from],
            "to": [json_number(c, 3) for c in elem_to],
            "faces": {
                direction: {
                    "uv": [
                        float(f"{(posx + 0.1) * 16 / tw:.6g}"),
                        float(f"{(posy + 0.1) * 16 / ty:.6g}"),
                        float(f"{(posx + 0.9) * 16 / tw:.6g}"),
                        float(f"{(posy + 0.9) * 16 / ty:.6g}"),
                    ],
                    "texture": "#0",
                    "tintindex": 0,
                }
            },
        }
        if rotation is not None:
            # An axis left out is 0 to the client.
            element["rotation"] = {"origin": rotation["origin"]}
            for axis in "xyz":
                angle = json_number(rotation[axis], 2)
                if angle:
                    element["rotation"][axis] = angle
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
    parser.add_argument("--centred", action="store_true", dest="centred", help="Carriers at the block centre, for a block the client offsets")
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
            centred=args.centred,
        )
    except ObjmcError as e:
        print(col.err + str(e) + col.end)
        sys.exit(1)


if __name__ == "__main__":
    main()
