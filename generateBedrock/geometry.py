"""Bedrock block geometry from a block's faces (mesh.Face).

Bedrock draws a custom block from a geometry file of bones, each with cubes
and, optionally, a `poly_mesh`. Every face is drawn the way that reproduces
it exactly where one exists:

- A JSON element stays one cube, with each face's uv rectangle. A blockstate's
  quarter turns are applied to the cube itself, so it stays on the grid; only
  an element turned by its own `rotation` (22.5 degrees and the like) becomes
  a rotated cube.
- A face of an `.obj` that is a rectangle, with its texture a rectangle too,
  becomes a cube of no thickness turned to lie where the face lies: exact, and
  drawn by every Bedrock version. In MCME's packs that is about 80 % of the
  `.obj` faces.
- Any other face, a triangle or a quad of another shape, can't be a cube face.
  The `hybrid` mode (the default) puts those in the bone's `poly_mesh`, the
  `polymesh` mode puts every `.obj` face there, and the `cubes` mode draws each
  as the rectangle around it instead.

Coordinates. Java's block space (mesh.py) puts the cell at 0..16 on each axis.
Bedrock's block geometry is centred on the block in x and z, and its files
mirror x: a point (x, y, z) of Java's space is (8 - x, y, z - 8) in the file.
How a file's cube is drawn follows Blockbench, the editor Bedrock's own
creators use: Blockbench reads a cube's file `rotation` (rx, ry, rz) as the
turn Rz(rz) * Ry(-ry) * Rx(-rx) about its pivot, in the unmirrored space, and
a face's uv as Java reads a face's, except that up and down faces run their uv
rectangle from the opposite corner. Rainbow, GeyserMC's converter, agrees on
the mirror and the faces.

Size. Mojang documents a limit for block geometry: with the block's own cell,
it must fit in a 30 x 30 x 30 pixel box, and Blockbench's block format keeps
models to it. MCME's `.obj` models often reach much further, as Java lets
them. Whether Bedrock holds a block's poly_mesh to the limit too isn't
documented, so geometry beyond it is kept whole by default (`oversize="keep"`);
`"polymesh"` puts every face of such a model in the poly_mesh, and `"clip"`
leaves out the faces outside the largest box that fits.
"""

import math
from collections import Counter
from dataclasses import dataclass, field

import mesh
from mesh import FACE_CORNERS, NORMALS, Face, box_corner, cross, dot, length, normalize, sub

MODES = ("hybrid", "polymesh", "cubes")
OVERSIZE = ("keep", "polymesh", "clip")

# Bedrock's limit on a block's geometry, in pixels, the block's cell included
LIMIT = 30.0
EPS = 1e-4
# Directions whose Bedrock uv rectangle starts at the opposite corner
FLIPPED_UV = ("up", "down")


@dataclass(frozen=True)
class Material:
    """What a face's material instance has to say: its texture and how it's lit."""

    texture: str
    tintindex: int = -1
    shade: bool = True
    ambient_occlusion: bool = True


def material_of(face: Face) -> Material:
    return Material(face.texture, face.tintindex, face.shade, face.ambient_occlusion)


@dataclass
class _Primitive:
    """A cube or a poly_mesh polygon, with its corners in Java's space for the size check."""

    vertices: list
    cube: dict | None = None
    # One of the cube's faces each: (direction, uv fit, material)
    cube_faces: list = field(default_factory=list)
    poly: Face | None = None


@dataclass
class BlockGeometry:
    """The geometry for one block state, ready for the pack and the Geyser mappings.

    Either `full_block` is set, and the state uses Bedrock's own full block
    with one material per side, or `geometry` is a "minecraft:geometry" entry
    of the pack, its identifier still to be given. Its faces name material
    instances: "*" for `slots[0]` and "m<i>" for `slots[i]`, so states whose
    models differ only in texture share one geometry.
    """

    full_block: dict[str, Material] | None = None
    geometry: dict | None = None
    slots: list[Material] = field(default_factory=list)
    uses_poly_mesh: bool = False
    dropped: int = 0  # faces left out for Bedrock's size limit
    oversize: bool = False  # reaches beyond the size limit, and is kept whole
    approximated: int = 0  # faces drawn as the rectangle around them

    def materials(self) -> dict[str, Material]:
        """Material instance name -> material."""
        if self.full_block is not None:
            names = dict(self.full_block)
            names["*"] = Counter(self.full_block.values()).most_common(1)[0][0]
            return names
        return {slot_name(i): m for i, m in enumerate(self.slots)}


def slot_name(index: int) -> str:
    return "*" if index == 0 else f"m{index}"


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------


def _close(a, b, eps=EPS):
    return abs(a - b) <= eps


def _same_point(a, b, eps=EPS):
    return all(abs(x - y) <= eps for x, y in zip(a, b))


def _num(value: float) -> float:
    value = round(value, 4)
    return 0.0 if value == 0 else value


def _file_point(p) -> list[float]:
    """A point of Java's block space in a Bedrock geometry file."""
    return [_num(8 - p[0]), _num(p[1]), _num(p[2] - 8)]


def _world_direction(normal) -> str | None:
    for name, n in NORMALS.items():
        if dot(normal, n) > 1 - 1e-6:
            return name
    return None


def _is_signed_permutation(m) -> bool:
    return all(_close(abs(v), 0, 1e-9) or _close(abs(v), 1, 1e-9) for row in m for v in row)


def _is_identity(m) -> bool:
    return all(_close(m[i][j], 1.0 if i == j else 0.0, 1e-9) for i in range(3) for j in range(3))


def fit_uv(uvs, allow_rotation: bool):
    """The uv rectangle and rotation that give a face's four corners these uvs.

    `uvs` are in the order of FACE_CORNERS for the face's direction. Returns
    (u0, v0, u1, v1, rotation), the face's uv as a JSON model would write it,
    or None when no rectangle does. A mirrored texture is a rectangle whose
    u1 < u0 or v1 < v0.
    """
    for rotation in (0, 90, 180, 270) if allow_rotation else (0,):
        shift = rotation // 90
        by_corner = [None] * 4
        for i in range(4):
            by_corner[(i + shift) % 4] = uvs[i]
        a, b, c, d = by_corner  # (u0, v0), (u0, v1), (u1, v1), (u1, v0)
        if _close(a[0], b[0]) and _close(c[0], d[0]) and _close(b[1], c[1]) and _close(d[1], a[1]):
            return (a[0], a[1], c[0], c[1], rotation)
    return None


def euler_zyx(m) -> tuple[float, float, float]:
    """Angles (x, y, z) in degrees with m = Rz(z) * Ry(y) * Rx(x), as three.js's 'ZYX' order."""
    sy = -max(-1.0, min(1.0, m[2][0]))
    y = math.asin(sy)
    if abs(m[2][0]) < 0.9999999:
        x = math.atan2(m[2][1], m[2][2])
        z = math.atan2(m[1][0], m[0][0])
    else:
        x = 0.0
        z = math.atan2(-m[0][1], m[1][1])
    return math.degrees(x), math.degrees(y), math.degrees(z)


def _file_rotation(m) -> list[float]:
    x, y, z = euler_zyx(m)
    return [_num(-x), _num(-y), _num(z)]


def _face_entry(direction: str, fit, slot: str) -> dict:
    u0, v0, u1, v1, rotation = fit
    if direction in FLIPPED_UV:
        entry = {"uv": [_num(u1), _num(v1)], "uv_size": [_num(u0 - u1), _num(v0 - v1)]}
    else:
        entry = {"uv": [_num(u0), _num(v0)], "uv_size": [_num(u1 - u0), _num(v1 - v0)]}
    if rotation:
        entry["uv_rotation"] = rotation
    if slot != "*":
        entry["material_instance"] = slot
    return entry


# --------------------------------------------------------------------------
# Rectangles
# --------------------------------------------------------------------------


def is_rect(face: Face) -> bool:
    """A planar rectangle whose texture is a rectangle on the texture's axes."""
    if len(face.corners) != 4:
        return False
    p0, p1, p2, p3 = face.corners
    e1, e2 = sub(p1, p0), sub(p3, p0)
    if length(e1) < EPS or length(e2) < EPS:
        return False
    if not _same_point(p2, mesh.add(p1, e2), 1e-3):
        return False
    if abs(dot(normalize(e1), normalize(e2))) > 1e-4:
        return False
    u0, u1, u2, u3 = face.uvs
    f1, f2 = sub(u1, u0), sub(u3, u0)
    on_axes = (_close(f1[0], 0, 1e-3) or _close(f1[1], 0, 1e-3)) and (
        _close(f2[0], 0, 1e-3) or _close(f2[1], 0, 1e-3)
    )
    return on_axes and _same_point(u2, mesh.add(u1, f2), 1e-3)


def merge_triangles(faces: list[Face]) -> list[Face]:
    """Pairs of triangles that together are a textured rectangle, as that rectangle.

    Modellers often split a quad into two triangles; as a rectangle it can be
    a cube face again.
    """
    triangles = [f for f in faces if len(f.corners) == 3]
    others = [f for f in faces if len(f.corners) != 3]
    used = set()
    merged = []
    for i, t1 in enumerate(triangles):
        if i in used:
            continue
        for j in range(i + 1, len(triangles)):
            if j in used:
                continue
            quad = _join(t1, triangles[j])
            if quad is not None and is_rect(quad):
                merged.append(quad)
                used.update((i, j))
                break
    return others + merged + [t for i, t in enumerate(triangles) if i not in used]


def _join(t1: Face, t2: Face) -> Face | None:
    if t1.texture != t2.texture or t1.tintindex != t2.tintindex or dot(t1.normal(), t2.normal()) < 1 - 1e-6:
        return None
    for a in range(3):
        p, q = a, (a + 1) % 3  # the edge p -> q of t1
        for b in range(3):
            r, s = b, (b + 1) % 3  # t2 must have it as q -> p
            if (
                _same_point(t1.corners[p], t2.corners[s])
                and _same_point(t1.corners[q], t2.corners[r])
                and _same_point(t1.uvs[p], t2.uvs[s], 1e-3)
                and _same_point(t1.uvs[q], t2.uvs[r], 1e-3)
            ):
                x = (q + 1) % 3  # t1 reads p, q, x
                y = (s + 1) % 3  # t2 reads q, p, y
                corners = (t1.corners[p], t2.corners[y], t1.corners[q], t1.corners[x])
                uvs = (t1.uvs[p], t2.uvs[y], t1.uvs[q], t1.uvs[x])
                return Face(corners=corners, uvs=uvs, texture=t1.texture, tintindex=t1.tintindex,
                            shade=t1.shade, ambient_occlusion=t1.ambient_occlusion)
    return None


def around_rect(face: Face) -> Face:
    """The rectangle around a face, in its plane, textured as near as a rectangle can be.

    For the `cubes` mode, and for faces a poly_mesh can't take: the triangle
    or odd quad becomes a rectangle along one of its edges that holds it -
    the edge whose rectangle keeps the face's texture mapping a rectangle
    (so the texture lands exactly where the face has it), else the smallest.
    Where no rectangle keeps the mapping, the texture is the rectangle around
    the face's uvs, turned to match the face's as closely as it can be.
    """
    n = face.normal()
    corners = face.corners
    best = None
    for i in range(len(corners)):
        edge = sub(corners[(i + 1) % len(corners)], corners[i])
        if length(edge) < EPS:
            continue
        e1 = normalize(edge)
        e2 = normalize(cross(n, e1))
        candidate = _rect_along(face, corners[i], e1, e2)
        exact = is_rect(candidate)
        area = length(sub(candidate.corners[1], candidate.corners[0])) * length(sub(candidate.corners[3], candidate.corners[0]))
        key = (not exact, round(area, 3))
        if best is None or key < best[0]:
            best = (key, candidate)
    (inexact, _), out = best
    if not inexact:
        return out
    us, vs = [uv[0] for uv in face.uvs], [uv[1] for uv in face.uvs]
    box = [(min(us), min(vs)), (max(us), min(vs)), (max(us), max(vs)), (min(us), max(vs))]
    orders = [box[k:] + box[:k] for k in range(4)]
    orders += [list(reversed(o)) for o in orders]  # mirrored
    uvs = min(orders, key=lambda o: sum(length(sub(a, b)) for a, b in zip(o, out.uvs)))
    return Face(corners=out.corners, uvs=tuple(uvs), texture=face.texture, tintindex=face.tintindex,
                shade=face.shade, ambient_occlusion=face.ambient_occlusion)


def _rect_along(face: Face, origin, e1, e2) -> Face:
    """The smallest rectangle with sides along e1 and e2 that holds the face, with the face's texture mapping."""
    st = [(dot(sub(c, origin), e1), dot(sub(c, origin), e2)) for c in face.corners]
    s0, s1 = min(s for s, _ in st), max(s for s, _ in st)
    t0, t1 = min(t for _, t in st), max(t for _, t in st)
    rect_st = [(s0, t0), (s1, t0), (s1, t1), (s0, t1)]  # counter-clockwise from the front
    rect = tuple(mesh.add(origin, mesh.add(mesh.scale(e1, s), mesh.scale(e2, t))) for s, t in rect_st)
    affine = mesh._solve_affine_2d(st, list(face.uvs))
    if affine is None:
        uvs = tuple(face.uvs[0] for _ in range(4))
    else:
        (a, b, c), (d, e, f) = affine
        uvs = tuple((a * s + b * t + c, d * s + e * t + f) for s, t in rect_st)
    return Face(corners=rect, uvs=uvs, texture=face.texture, tintindex=face.tintindex,
                shade=face.shade, ambient_occlusion=face.ambient_occlusion)


# --------------------------------------------------------------------------
# Cubes
# --------------------------------------------------------------------------


def _cube(lo, hi, rotation=None, pivot=None) -> dict:
    size = [_num(hi[i] - lo[i]) for i in range(3)]
    cube = {"origin": [_num(8 - hi[0]), _num(lo[1]), _num(lo[2] - 8)], "size": size}
    if rotation is not None and not _is_identity(rotation):
        cube["pivot"] = _file_point(pivot)
        cube["rotation"] = _file_rotation(rotation)
    return cube


def _box_vertices(lo, hi, rotation=None, pivot=None):
    corners = [box_corner(lo, hi, (i & 1, (i >> 1) & 1, (i >> 2) & 1)) for i in range(8)]
    if rotation is None:
        return corners
    return [mesh.rotate_about(rotation, c, pivot) for c in corners]


def _unit_axes(direction):
    """The unit box's (first edge, second edge) of a face, in FaceInfo order."""
    c = [box_corner((0, 0, 0), (1, 1, 1), pick) for pick in FACE_CORNERS[direction]]
    return normalize(sub(c[1], c[0])), normalize(sub(c[2], c[1]))


def _flat_cube(face: Face, slot: str, allow_rotation: bool) -> _Primitive | None:
    """A rectangle face as one face of a cube of no thickness."""
    direction = _world_direction(face.normal())
    if direction is not None:
        lo = tuple(min(c[i] for c in face.corners) for i in range(3))
        hi = tuple(max(c[i] for c in face.corners) for i in range(3))
        canonical = [box_corner(lo, hi, pick) for pick in FACE_CORNERS[direction]]
        order = [next((j for j, c in enumerate(face.corners) if _same_point(c, k, 1e-3)), None) for k in canonical]
        if None not in order and len(set(order)) == 4:
            fit = fit_uv([face.uvs[j] for j in order], allow_rotation)
            if fit is not None:
                return _Primitive(vertices=list(face.corners), cube=_cube(lo, hi, None),
                                  cube_faces=[(direction, fit, slot)])

    # Turned: the face direction and corner order that need the least turn
    best = None
    for candidate in FACE_CORNERS:
        a, b = _unit_axes(candidate)
        n = NORMALS[candidate]
        frame = (a, b, n)
        for k in range(4):
            corners = [face.corners[(i + k) % 4] for i in range(4)]
            uvs = [face.uvs[(i + k) % 4] for i in range(4)]
            fit = fit_uv(uvs, False)
            if fit is None:
                continue
            ea = normalize(sub(corners[1], corners[0]))
            eb = normalize(sub(corners[2], corners[1]))
            en = cross(ea, eb)
            # rotation taking the unit face's frame (a, b, n) to the face's (ea, eb, en)
            target = (ea, eb, en)
            m = tuple(tuple(sum(target[k2][i] * frame[k2][j] for k2 in range(3)) for j in range(3)) for i in range(3))
            angle = math.acos(max(-1.0, min(1.0, (m[0][0] + m[1][1] + m[2][2] - 1) / 2)))
            if best is None or angle < best[0] - 1e-9:
                best = (angle, candidate, m, corners, fit)
    if best is None:
        return None
    _, direction, m, corners, fit = best
    pivot = corners[0]
    back = mesh.transpose(m)
    local = [mesh.rotate_about(back, c, pivot) for c in corners]
    lo = tuple(min(c[i] for c in local) for i in range(3))
    hi = tuple(max(c[i] for c in local) for i in range(3))
    return _Primitive(vertices=list(face.corners), cube=_cube(lo, hi, m, pivot),
                      cube_faces=[(direction, fit, slot)])


def _element_cube(faces: list[Face], slots, allow_rotation: bool):
    """One JSON element's faces as one cube: (primitive, faces it couldn't take)."""
    box = faces[0].box
    if _is_signed_permutation(box.rotation):
        # Turned only by quarter turns: the turned box, with no rotation of its own
        vertices = _box_vertices(box.lo, box.hi, box.rotation, box.pivot)
        lo = tuple(min(v[i] for v in vertices) for i in range(3))
        hi = tuple(max(v[i] for v in vertices) for i in range(3))
        rotation = pivot = None
    else:
        lo, hi, rotation, pivot = box.lo, box.hi, box.rotation, box.pivot
        vertices = _box_vertices(lo, hi, rotation, pivot)
    if sum(1 for i in range(3) if hi[i] - lo[i] < EPS) > 1:
        return None, []

    taken, left = [], []
    for face in faces:
        if rotation is None:
            direction = _world_direction(face.normal())
            if direction is None or any(d == direction for d, _, _ in taken):
                left.append(face)
                continue
            canonical = [box_corner(lo, hi, pick) for pick in FACE_CORNERS[direction]]
            order = [next((j for j, c in enumerate(face.corners) if _same_point(c, k, 1e-3)), None)
                     for k in canonical]
            if None in order:
                left.append(face)
                continue
            uvs = [face.uvs[j] for j in order]
        else:
            direction = face.direction
            uvs = list(face.uvs)
        fit = fit_uv(uvs, allow_rotation)
        if fit is None:
            left.append(face)
            continue
        taken.append((direction, fit, slots(face)))
    if not taken:
        return None, left
    return _Primitive(vertices=vertices, cube=_cube(lo, hi, rotation, pivot), cube_faces=taken), left


# --------------------------------------------------------------------------
# The size limit
# --------------------------------------------------------------------------


def _window(extents) -> float:
    """The start of the 30-pixel window, holding the cell, that holds the most extents."""
    starts = {-(LIMIT - 16.0), 0.0}
    for lo, hi in extents:
        for start in (lo, hi - LIMIT):
            if -(LIMIT - 16.0) - EPS <= start <= EPS:
                starts.add(start)
    return max(sorted(starts, key=lambda s: abs(s + (LIMIT - 16) / 2)),
               key=lambda s: sum(1 for lo, hi in extents if lo >= s - EPS and hi <= s + LIMIT + EPS))


def _fits(primitives) -> bool:
    for axis in range(3):
        lo = min([0.0] + [v[axis] for p in primitives for v in p.vertices])
        hi = max([16.0] + [v[axis] for p in primitives for v in p.vertices])
        if hi - lo > LIMIT + EPS:
            return False
    return True


def _clip(primitives):
    """(kept, dropped count): the primitives inside the best 30-pixel box."""
    windows = []
    for axis in range(3):
        extents = [(min(v[axis] for v in p.vertices), max(v[axis] for v in p.vertices)) for p in primitives]
        windows.append(_window(extents))
    kept = [
        p for p in primitives
        if all(min(v[a] for v in p.vertices) >= windows[a] - EPS and max(v[a] for v in p.vertices) <= windows[a] + LIMIT + EPS
               for a in range(3))
    ]
    return kept, len(primitives) - len(kept)


# --------------------------------------------------------------------------
# Building a block's geometry
# --------------------------------------------------------------------------


def build(faces: list[Face], mode: str = "hybrid", oversize: str = "keep", reverse_poly_winding: bool = False):
    """The Bedrock geometry for a block state's faces, or None when nothing is drawn."""
    if mode not in MODES:
        raise ValueError(f"unknown geometry mode {mode!r}")
    if oversize not in OVERSIZE:
        raise ValueError(f"unknown oversize handling {oversize!r}")
    faces = [f for f in faces if len(f.corners) >= 3 and length(cross(sub(f.corners[1], f.corners[0]), sub(f.corners[2], f.corners[0]))) > 1e-9]
    if not faces:
        return None

    boxes: dict[mesh.Box, list[Face]] = {}
    loose: list[Face] = []
    for face in faces:
        if face.box is not None and len(face.corners) == 4:
            boxes.setdefault(face.box, []).append(face)
        else:
            loose.append(face)
    loose = merge_triangles(loose)

    rects = [f for f in loose if is_rect(f)]
    others = [f for f in loose if not is_rect(f)]
    poly_faces: list[Face] = []
    if mode == "polymesh":
        poly_faces, rects, others = loose, [], []
    elif mode == "hybrid":
        poly_faces, others = others, []

    result = BlockGeometry()
    # A poly_mesh polygon can only be drawn with the "*" material, so a second
    # texture among them is drawn as cubes
    if poly_faces:
        main = Counter(material_of(f) for f in poly_faces).most_common(1)[0][0]
        stray = [f for f in poly_faces if material_of(f) != main]
        poly_faces = [f for f in poly_faces if material_of(f) == main]
        others += stray
        result.slots.append(main)
    allow_rotation = not poly_faces
    approximated = [around_rect(f) for f in others]
    result.approximated = len(approximated)
    rects += approximated

    def slot(face):
        material = material_of(face)
        if material not in result.slots:
            result.slots.append(material)
        return slot_name(result.slots.index(material))

    primitives: list[_Primitive] = []
    for group in boxes.values():
        primitive, left = _element_cube(group, slot, allow_rotation)
        if primitive is not None:
            primitives.append(primitive)
        rects += [f for f in left if is_rect(f)]
        poly_faces += [f for f in left if not is_rect(f)]  # never happens for a JSON model
    for face in rects:
        primitive = _flat_cube(face, slot(face), allow_rotation)
        if primitive is not None:
            primitives.append(primitive)
    primitives += [_Primitive(vertices=list(f.corners), poly=f) for f in poly_faces]

    if not _fits(primitives):
        if oversize == "clip":
            primitives, result.dropped = _clip(primitives)
        elif oversize == "polymesh" and mode != "polymesh":
            # JSON elements stay cubes; only the .obj faces move to the poly_mesh
            again = build(faces, mode="polymesh", oversize="keep", reverse_poly_winding=reverse_poly_winding)
            if again is not None:
                again.oversize = True
            return again
        else:
            result.oversize = True
    if not primitives:
        return None

    full = _full_block(primitives)
    if full is not None:
        result.full_block = {d: result.slots[_slot_index(s)] for d, s in full.items()}
        result.slots = []
        return result

    cubes = []
    for p in primitives:
        if p.cube is not None:
            cube = dict(p.cube)
            cube["uv"] = {d: _face_entry(d, fit, s) for d, fit, s in p.cube_faces}
            cubes.append(cube)
    polys = [p.poly for p in primitives if p.poly is not None]
    bone = {"name": "block", "pivot": [0, 0, 0]}
    if cubes:
        bone["cubes"] = cubes
    if polys:
        bone["poly_mesh"] = _poly_mesh(polys, reverse_poly_winding)
        result.uses_poly_mesh = True
    if not result.slots:
        return None
    result.geometry = {
        "format_version": "1.12.0" if polys else "1.21.0",
        "minecraft:geometry": [
            {
                "description": {"identifier": None, "texture_width": 16, "texture_height": 16, **_visible_bounds(primitives)},
                "bones": [bone],
            }
        ],
    }
    return result


def _slot_index(name: str) -> int:
    return 0 if name == "*" else int(name[1:])


def _full_block(primitives) -> dict[str, str] | None:
    """direction -> material slot, when the state is one whole, plainly textured cube."""
    if len(primitives) != 1 or primitives[0].cube is None or "rotation" in primitives[0].cube:
        return None
    p = primitives[0]
    if p.cube["origin"] != [-8.0, 0.0, -8.0] or p.cube["size"] != [16.0, 16.0, 16.0] or len(p.cube_faces) != 6:
        return None
    sides = {}
    for direction, fit, slot in p.cube_faces:
        if fit != (0.0, 0.0, 16.0, 16.0, 0):
            return None
        sides[direction] = slot
    return sides


def _poly_mesh(faces: list[Face], reverse: bool) -> dict:
    """A poly_mesh of the faces, as Bedrock's own and the example meshes write it.

    Positions and normals mirror x like the rest of the file, the uvs are
    normalised with v up, and each polygon lists [position, normal, uv]
    indices in the face's own order, a triangle repeating its first corner:
    Bedrock draws a poly_mesh of quads only.
    """
    positions, normals, uvs, polys = {}, {}, {}, []

    def index(table, value):
        key = tuple(_num(v) for v in value)
        if key not in table:
            table[key] = len(table)
        return table[key]

    for face in faces:
        n = face.normal()
        normal = index(normals, (-n[0], n[1], n[2]))
        corners = [
            [index(positions, _file_point(c)), normal, index(uvs, (uv[0] / 16, 1 - uv[1] / 16))]
            for c, uv in zip(face.corners, face.uvs)
        ]
        if reverse:
            corners.reverse()
        while len(corners) < 4:
            corners.append(corners[0])
        polys.append(corners)
    return {
        "normalized_uvs": True,
        "positions": [list(k) for k in positions],
        "normals": [list(k) for k in normals],
        "uvs": [list(k) for k in uvs],
        "polys": polys,
    }


def _visible_bounds(primitives) -> dict:
    vertices = [v for p in primitives for v in p.vertices]
    reach = max([8.0] + [max(abs(v[0] - 8), abs(v[2] - 8)) for v in vertices])
    lo = min([0.0] + [v[1] for v in vertices])
    hi = max([16.0] + [v[1] for v in vertices])
    return {
        "visible_bounds_width": math.ceil(reach * 2 / 16 + 1),
        "visible_bounds_height": math.ceil((hi - lo) / 16 + 1),
        "visible_bounds_offset": [0, _num((hi + lo) / 32), 0],
    }
