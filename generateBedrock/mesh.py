"""Block models as plain textured faces, the form every model is converted from.

Java draws a block from two kinds of model: the JSON models of vanilla, whose
elements are boxes, and MCME's `.obj` models, which Special Model Loader reads.
Both become a list of `Face`s here: three or four corners in Java's block
space, each with its texture coordinate, so the Bedrock side (geometry.py)
never needs to know which kind of model a face came from.

Java's block space is in pixels, with the block's cell from 0 to 16 on each
axis: x east, y up, z south. A face's corners run counter-clockwise seen from
its front, as Minecraft's own FaceInfo orders them, and only the front is drawn.
Texture coordinates are in pixels of a 16 x 16 texture with v down, the units
of a JSON model's `uv`, whatever the texture's real size.

The JSON element rules follow Minecraft's FaceBakery and BlockModelRotation,
so a face lands where Java draws it, with the texture turned as Java turns it.
"""

import itertools
import math
from dataclasses import dataclass, field, replace

# --------------------------------------------------------------------------
# Small vector helpers: tuples, so faces stay hashable and cheap to copy
# --------------------------------------------------------------------------

Vec3 = tuple[float, float, float]
Vec2 = tuple[float, float]
Matrix = tuple[Vec3, Vec3, Vec3]  # rows

IDENTITY: Matrix = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
BLOCK_CENTRE: Vec3 = (8.0, 8.0, 8.0)


def add(a, b):
    return tuple(x + y for x, y in zip(a, b))


def sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def scale(a, s):
    return tuple(x * s for x in a)


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def cross(a: Vec3, b: Vec3) -> Vec3:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def length(a):
    return math.sqrt(dot(a, a))


def normalize(a):
    n = length(a)
    return tuple(x / n for x in a) if n > 1e-12 else tuple(0.0 for _ in a)


def mat_vec(m: Matrix, v: Vec3) -> Vec3:
    return (dot(m[0], v), dot(m[1], v), dot(m[2], v))


def mat_mul(a: Matrix, b: Matrix) -> Matrix:
    columns = list(zip(*b))
    return tuple(tuple(dot(row, col) for col in columns) for row in a)  # type: ignore[return-value]


def transpose(m: Matrix) -> Matrix:
    return tuple(zip(*m))  # type: ignore[return-value]


def rotation(axis: str, degrees: float) -> Matrix:
    """A right-handed rotation: counter-clockwise looking down the axis at the origin."""
    c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    # Exact for the quarter turns blockstates use, so rotated boxes stay on the grid
    c, s = (round(c) if abs(c - round(c)) < 1e-12 else c), (round(s) if abs(s - round(s)) < 1e-12 else s)
    if axis == "x":
        return ((1, 0, 0), (0, c, -s), (0, s, c))
    if axis == "y":
        return ((c, 0, s), (0, 1, 0), (-s, 0, c))
    return ((c, -s, 0), (s, c, 0), (0, 0, 1))


def rotate_about(m: Matrix, point: Vec3, centre: Vec3) -> Vec3:
    return add(mat_vec(m, sub(point, centre)), centre)


# --------------------------------------------------------------------------
# Faces
# --------------------------------------------------------------------------

DIRECTIONS = ("down", "up", "north", "south", "west", "east")
NORMALS: dict[str, Vec3] = {
    "down": (0, -1, 0),
    "up": (0, 1, 0),
    "north": (0, 0, -1),
    "south": (0, 0, 1),
    "west": (-1, 0, 0),
    "east": (1, 0, 0),
}


@dataclass(frozen=True)
class Face:
    """One textured polygon of a block model."""

    corners: tuple[Vec3, ...]  # 3 or 4, counter-clockwise from the front
    uvs: tuple[Vec2, ...]  # one per corner, 0..16 pixels, v down
    texture: str  # a texture identifier, "mcme:block/apple_leaves"
    tintindex: int = -1  # Java's tintindex; -1 is untinted
    shade: bool = True  # Java's element "shade": directional shading
    ambient_occlusion: bool = True  # the model's "ambientocclusion"
    # Set for a face that came from a JSON element, so geometry.py can keep the
    # element's six faces together as one Bedrock cube
    box: "Box | None" = None
    direction: str | None = None  # the face of `box` this is

    def normal(self) -> Vec3:
        """The direction the front faces."""
        a, b, c = self.corners[0], self.corners[1], self.corners[2]
        return normalize(cross(sub(b, a), sub(c, b)))


@dataclass(frozen=True)
class Box:
    """A JSON element's box: where it is before its rotations, and how it's turned.

    A point p of the box ends up at `rotation · (p - pivot) + pivot`. Every
    face of the element shares one, so the element stays one cube on Bedrock.
    """

    lo: Vec3
    hi: Vec3
    rotation: Matrix = IDENTITY
    pivot: Vec3 = BLOCK_CENTRE
    element: int = 0  # tells apart two elements with the same box

    def place(self, point: Vec3) -> Vec3:
        return rotate_about(self.rotation, point, self.pivot)


# The corners of each face of a box, as Minecraft's FaceInfo orders them:
# counter-clockwise from outside. Each is (x, y, z) with 0 for the box's low
# end and 1 for its high end.
FACE_CORNERS: dict[str, tuple[tuple[int, int, int], ...]] = {
    "down": ((0, 0, 1), (0, 0, 0), (1, 0, 0), (1, 0, 1)),
    "up": ((0, 1, 0), (0, 1, 1), (1, 1, 1), (1, 1, 0)),
    "north": ((1, 1, 0), (1, 0, 0), (0, 0, 0), (0, 1, 0)),
    "south": ((0, 1, 1), (0, 0, 1), (1, 0, 1), (1, 1, 1)),
    "west": ((0, 1, 0), (0, 0, 0), (0, 0, 1), (0, 1, 1)),
    "east": ((1, 1, 1), (1, 0, 1), (1, 0, 0), (1, 1, 0)),
}


def box_corner(lo: Vec3, hi: Vec3, pick) -> Vec3:
    return tuple(hi[i] if pick[i] else lo[i] for i in range(3))  # type: ignore[return-value]


def default_uv(direction: str, lo: Vec3, hi: Vec3) -> tuple[float, float, float, float]:
    """The uv a JSON face gets when it names none (FaceBakery.defaultFaceUV)."""
    if direction == "down":
        return (lo[0], 16 - hi[2], hi[0], 16 - lo[2])
    if direction == "up":
        return (lo[0], lo[2], hi[0], hi[2])
    if direction == "north":
        return (16 - hi[0], 16 - hi[1], 16 - lo[0], 16 - lo[1])
    if direction == "south":
        return (lo[0], 16 - hi[1], hi[0], 16 - lo[1])
    if direction == "west":
        return (lo[2], 16 - hi[1], hi[2], 16 - lo[1])
    return (16 - hi[2], 16 - hi[1], 16 - lo[2], 16 - lo[1])


def rect_corner_uvs(uv, rotation_degrees: int) -> tuple[Vec2, ...]:
    """The texture coordinate of each of a face's four corners, in FaceInfo order.

    Corner i takes the uv rectangle's corner (i + rotation / 90) mod 4, where
    the rectangle's corners run (u0, v0), (u0, v1), (u1, v1), (u1, v0): the
    rule of Minecraft's BlockElementFace.UVs, which turns the texture clockwise.
    """
    u0, v0, u1, v1 = uv
    rect = ((u0, v0), (u0, v1), (u1, v1), (u1, v0))
    shift = (rotation_degrees // 90) % 4
    return tuple(rect[(i + shift) % 4] for i in range(4))


# --------------------------------------------------------------------------
# JSON elements
# --------------------------------------------------------------------------


class ModelError(ValueError):
    """A model that can't be read the way Java reads it."""


_ELEMENT_IDS = itertools.count(1)


def _number_triplet(value, what):
    if not (isinstance(value, list) and len(value) == 3 and all(isinstance(v, (int, float)) for v in value)):
        raise ModelError(f"{what} isn't three numbers: {value!r}")
    return tuple(float(v) for v in value)


def _element_rotation(element) -> tuple[Matrix, Vec3, Vec3]:
    """(rotation, pivot, rescale factors) of an element's own "rotation"."""
    spec = element.get("rotation")
    if not spec:
        return IDENTITY, BLOCK_CENTRE, (1.0, 1.0, 1.0)
    origin = _number_triplet(spec.get("origin", [8, 8, 8]), "rotation origin")
    if "axis" in spec:
        axis = spec["axis"]
        angle = float(spec.get("angle", 0))
        if axis not in ("x", "y", "z"):
            raise ModelError(f"rotation axis isn't x, y or z: {axis!r}")
        matrix = rotation(axis, angle)
        factors = [1.0, 1.0, 1.0]
        if spec.get("rescale") and abs(math.cos(math.radians(angle))) > 1e-6:
            # FaceBakery stretches the two axes the rotation turns by 1 / cos
            stretch = 1 / abs(math.cos(math.radians(angle)))
            for i, other in enumerate("xyz"):
                if other != axis:
                    factors[i] = stretch
        return matrix, origin, tuple(factors)  # type: ignore[return-value]
    # 1.21.11 and later: free rotation as x, y and z angles, applied x, then y, then z
    matrix = IDENTITY
    for axis in "xyz":
        angle = float(spec.get(axis, 0))
        if angle:
            matrix = mat_mul(rotation(axis, angle), matrix)
    return matrix, origin, (1.0, 1.0, 1.0)


def element_faces(element, textures: dict[str, str], ambient_occlusion: bool) -> list[Face]:
    """The faces of one JSON element, in block space, before any blockstate rotation.

    `textures` maps a face's "#name" to the texture identifier it resolves to.
    A face whose texture doesn't resolve is left out, as Java draws it with the
    missing texture.
    """
    lo = _number_triplet(element.get("from"), "element from")
    hi = _number_triplet(element.get("to"), "element to")
    lo, hi = tuple(min(a, b) for a, b in zip(lo, hi)), tuple(max(a, b) for a, b in zip(lo, hi))
    matrix, pivot, factors = _element_rotation(element)
    if factors != (1.0, 1.0, 1.0):
        # Stretch about the pivot first, so the rotation turns the stretched box
        lo = tuple(pivot[i] + (lo[i] - pivot[i]) * factors[i] for i in range(3))
        hi = tuple(pivot[i] + (hi[i] - pivot[i]) * factors[i] for i in range(3))
    box = Box(lo, hi, matrix, pivot, next(_ELEMENT_IDS))  # type: ignore[arg-type]
    shade = element.get("shade", True) is not False

    faces = []
    for direction, spec in (element.get("faces") or {}).items():
        if direction not in FACE_CORNERS or not isinstance(spec, dict):
            continue
        texture = face_texture(spec.get("texture"), textures)
        if texture is None:
            continue
        uv = spec.get("uv")
        if isinstance(uv, list) and len(uv) == 4 and all(isinstance(v, (int, float)) for v in uv):
            uv = tuple(float(v) for v in uv)
        else:
            # The default is worked out from the box before any stretching
            original_lo = _number_triplet(element.get("from"), "element from")
            original_hi = _number_triplet(element.get("to"), "element to")
            uv = default_uv(
                direction,
                tuple(min(a, b) for a, b in zip(original_lo, original_hi)),
                tuple(max(a, b) for a, b in zip(original_lo, original_hi)),
            )
        rotation_degrees = int(spec.get("rotation", 0)) % 360
        corners = tuple(box.place(box_corner(lo, hi, pick)) for pick in FACE_CORNERS[direction])  # type: ignore[arg-type]
        faces.append(
            Face(
                corners=corners,
                uvs=rect_corner_uvs(uv, rotation_degrees),
                texture=texture,
                tintindex=int(spec.get("tintindex", -1)),
                shade=shade,
                ambient_occlusion=ambient_occlusion,
                box=box,
                direction=direction,
            )
        )
    return faces


def face_texture(ref, textures: dict[str, str]) -> str | None:
    """The texture a face's "texture" names, through the model's texture variables.

    A face always names a variable, "#side" or just "side"; a variable holds
    a texture identifier or "#" and another variable's name.
    """
    if not isinstance(ref, str):
        return None
    value = textures.get(ref.removeprefix("#"))
    for _ in range(32):
        if not isinstance(value, str):
            return None
        if not value.startswith("#"):
            return value
        value = textures.get(value[1:])
    return None


# --------------------------------------------------------------------------
# Blockstate rotation
# --------------------------------------------------------------------------


def blockstate_rotation(x: int, y: int, z: int = 0) -> Matrix:
    """The turn of a blockstate entry's "x", "y" and "z": z, then x, then y.

    Java's y=90 turns a model's north side to the east, which is a negative
    turn about y in a right-handed frame, and x=90 turns north to down; all
    three are BlockModelRotation's rotateYXZ(-y, -x, -z).
    """
    return mat_mul(rotation("y", -y), mat_mul(rotation("x", -x), rotation("z", -z)))


def rotate_faces(faces: list[Face], x: int, y: int, uvlock: bool, z: int = 0) -> list[Face]:
    """Faces turned as a blockstate entry turns them, about the block's centre.

    With uvlock the texture stays where it lies in the world instead of
    turning with the face, as Java's uvlock does for a JSON model.
    """
    if not (x % 360 or y % 360 or z % 360):
        return faces
    matrix = blockstate_rotation(x, y, z)
    turned = []
    for face in faces:
        corners = tuple(rotate_about(matrix, c, BLOCK_CENTRE) for c in face.corners)
        uvs = face.uvs
        box = face.box
        if box is not None:
            # The element keeps its own turn inside the blockstate's
            pivot = rotate_about(matrix, box.pivot, BLOCK_CENTRE)
            shift = sub(pivot, box.pivot)
            box = Box(add(box.lo, shift), add(box.hi, shift), mat_mul(matrix, box.rotation), pivot, box.element)  # type: ignore[arg-type]
            if uvlock and face.direction is not None:
                uvs = _uvlock(face, matrix)
        turned.append(replace(face, corners=corners, uvs=uvs, box=box))
    return turned


def _world_direction(normal: Vec3) -> str | None:
    for name, n in NORMALS.items():
        if dot(normal, n) > 0.999:
            return name
    return None


def _default_uv_at(direction: str, point: Vec3) -> Vec2:
    """Where a block-space point lies in a face's default texture mapping.

    `default_uv` is this mapping applied to a box's corners: an affine map
    from the face's plane to texture space.
    """
    x, y, z = point
    return {
        "down": (x, 16 - z),
        "up": (x, z),
        "north": (16 - x, 16 - y),
        "south": (x, 16 - y),
        "west": (z, 16 - y),
        "east": (16 - z, 16 - y),
    }[direction]


def _uvlock(face: Face, matrix: Matrix) -> tuple[Vec2, ...]:
    """The face's texture coordinates with the texture held still in the world.

    Java's uvlock counter-turns each face's texture so that, after the
    blockstate's turn, it lies as the default mapping of the face's new
    direction would lay it. That is one affine map A of texture space with
    A(default_old(q)) = default_new(turn(q)) for every point q of the face, and
    A applied to every corner's uv.
    """
    old = face.direction
    new = _world_direction(mat_vec(matrix, NORMALS[old]))  # type: ignore[index]
    if old is None or new is None:
        return face.uvs
    # Three points of the face's plane, and where the turn takes them
    # Points off the plane are fine: both mappings ignore the normal axis
    plane = [(0.0, 0.0, 0.0), (16.0, 0.0, 0.0), (0.0, 16.0, 0.0), (0.0, 0.0, 16.0)]
    sources = [_default_uv_at(old, q) for q in plane]
    targets = [_default_uv_at(new, rotate_about(matrix, q, BLOCK_CENTRE)) for q in plane]
    affine = _solve_affine_2d(sources, targets)
    if affine is None:
        return face.uvs
    (a, b, c), (d, e, f) = affine
    return tuple((a * u + b * v + c, d * u + e * v + f) for u, v in face.uvs)


def _solve_affine_2d(sources, targets):
    """The affine map taking three of `sources` to the matching `targets`."""
    for i in range(len(sources)):
        for j in range(i + 1, len(sources)):
            for k in range(j + 1, len(sources)):
                (x1, y1), (x2, y2), (x3, y3) = sources[i], sources[j], sources[k]
                det = (x2 - x1) * (y3 - y1) - (x3 - x1) * (y2 - y1)
                if abs(det) < 1e-9:
                    continue
                rows = []
                for axis in range(2):
                    t1, t2, t3 = targets[i][axis], targets[j][axis], targets[k][axis]
                    a = ((t2 - t1) * (y3 - y1) - (t3 - t1) * (y2 - y1)) / det
                    b = ((x2 - x1) * (t3 - t1) - (x3 - x1) * (t2 - t1)) / det
                    rows.append((a, b, t1 - a * x1 - b * y1))
                return tuple(rows)
    return None


# --------------------------------------------------------------------------
# .obj models
# --------------------------------------------------------------------------


@dataclass
class ObjModel:
    """The faces of an `.obj`, before its texture is known."""

    faces: list[tuple[tuple[Vec3, ...], tuple[Vec2, ...]]] = field(default_factory=list)
    materials: set[str] = field(default_factory=set)


def read_obj(text: str, flip_v: bool) -> ObjModel:
    """An `.obj` file's faces, in block space with Java's texture coordinates.

    Special Model Loader reads `.obj` positions in blocks, with the block's
    cell from 0 to 1, and `flip_v` (true in every MCME model) turns the file's
    bottom-up texture coordinates into Java's top-down ones. A face with more
    than four corners is split into a fan of triangles.
    """
    positions, uvs = [], []
    model = ObjModel()
    for line in text.splitlines():
        parts = line.split()
        if not parts:
            continue
        kind = parts[0]
        if kind == "v" and len(parts) >= 4:
            positions.append(tuple(float(p) * 16 for p in parts[1:4]))
        elif kind == "vt" and len(parts) >= 3:
            u, v = float(parts[1]), float(parts[2])
            uvs.append((u * 16, (1 - v) * 16 if flip_v else v * 16))
        elif kind == "usemtl" and len(parts) >= 2:
            model.materials.add(parts[1])
        elif kind == "f" and len(parts) >= 4:
            corners, corner_uvs = [], []
            for ref in parts[1:]:
                indices = ref.split("/")
                corners.append(positions[_obj_index(indices[0], len(positions))])
                if len(indices) > 1 and indices[1]:
                    corner_uvs.append(uvs[_obj_index(indices[1], len(uvs))])
                else:
                    corner_uvs.append((0.0, 0.0))
            for polygon in _fan(corners, corner_uvs):
                model.faces.append(polygon)
    return model


def _obj_index(value: str, count: int) -> int:
    index = int(value)
    return index - 1 if index > 0 else count + index


def _fan(corners, uvs):
    if len(corners) <= 4:
        yield tuple(corners), tuple(uvs)
        return
    for i in range(1, len(corners) - 1):
        yield (corners[0], corners[i], corners[i + 1]), (uvs[0], uvs[i], uvs[i + 1])


def obj_faces(model: ObjModel, texture: str) -> list[Face]:
    """The `.obj`'s faces with their texture. Every face reads the one texture, as on Java."""
    faces = []
    for corners, uvs in model.faces:
        corners, uvs = _drop_repeated_corners(corners, uvs)
        if len(corners) >= 3:
            faces.append(Face(corners=corners, uvs=uvs, texture=texture))
    return faces


def _drop_repeated_corners(corners, uvs):
    """A quad that repeats a corner is the triangle it draws."""
    kept_corners, kept_uvs = [], []
    for corner, uv in zip(corners, uvs):
        if kept_corners and length(sub(corner, kept_corners[-1])) < 1e-6:
            continue
        kept_corners.append(corner)
        kept_uvs.append(uv)
    while len(kept_corners) > 1 and length(sub(kept_corners[0], kept_corners[-1])) < 1e-6:
        kept_corners.pop()
        kept_uvs.pop()
    return tuple(kept_corners), tuple(kept_uvs)
