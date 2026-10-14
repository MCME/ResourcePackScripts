"""generateBedrock's geometry: every face must come back exactly from what Bedrock reads.

No Bedrock runs here, so the geometry files are read back the way Blockbench
reads them (`read_cube` is its bedrock.js parseCube, transcribed): a mistake
in the sign of a rotation, the mirror or a uv shows up as a face that comes
back elsewhere, or with its texture turned. The poly_mesh is read back the
way the Blockbench plugin Meshy reads one, which matches the example meshes.
"""

import json
import math
import os
import random
from pathlib import Path

import geometry
import mesh
import pytest
from mesh import FACE_CORNERS, Face

# --------------------------------------------------------------------------
# Reading Bedrock geometry back, independently of geometry.py
# --------------------------------------------------------------------------


def _rz_ry_rx(x, y, z):
    """three.js Euler order 'ZYX' (Blockbench's for Bedrock): Rz(z) * Ry(y) * Rx(x), degrees."""
    return mesh.mat_mul(mesh.rotation("z", z), mesh.mat_mul(mesh.rotation("y", y), mesh.rotation("x", x)))


def read_cube(cube):
    """Each drawn face of a geometry cube as {(java position, uv)} plus its front normal.

    Blockbench's parseCube: x is mirrored, the rotation's x and y are negated,
    and up/down faces read their uv from the opposite corner.
    """
    size = cube["size"]
    origin = cube["origin"]
    lo = [-(origin[0] + size[0]), origin[1], origin[2]]
    hi = [lo[i] + size[i] for i in range(3)]
    pivot = cube.get("pivot", [0, 0, 0])
    pivot = [-pivot[0], pivot[1], pivot[2]]
    rx, ry, rz = cube.get("rotation", [0, 0, 0])
    matrix = _rz_ry_rx(-rx, -ry, rz)
    faces = []
    for direction, entry in cube["uv"].items():
        u, v = entry["uv"]
        su, sv = entry["uv_size"]
        uv = [u, v, u + su, v + sv]
        if direction in ("up", "down"):
            uv = [uv[2], uv[3], uv[0], uv[1]]
        uvs = mesh.rect_corner_uvs(uv, entry.get("uv_rotation", 0))
        corners = []
        for pick in FACE_CORNERS[direction]:
            display = mesh.rotate_about(matrix, mesh.box_corner(lo, hi, pick), pivot)
            corners.append((display[0] + 8, display[1], display[2] + 8))
        normal = mesh.mat_vec(matrix, mesh.NORMALS[direction])
        faces.append((corners, uvs, normal, entry.get("material_instance", "*")))
    return faces


def read_poly_mesh(poly_mesh):
    """Each polygon as (java corners, uvs 0..16 v down), Meshy's way."""
    out = []
    for poly in poly_mesh["polys"]:
        corners, uvs = [], []
        for p, _, t in poly:
            x, y, z = poly_mesh["positions"][p]
            u, v = poly_mesh["uvs"][t]
            corner, uv = (8 - x, y, z + 8), (u * 16, (1 - v) * 16)
            if corners and _close(corner, corners[0]) and _close(uv, uvs[0]):
                continue  # a triangle's repeated first corner
            corners.append(corner)
            uvs.append(uv)
        out.append((corners, uvs))
    return out


def _close(a, b, eps=2e-3):
    return all(abs(x - y) <= eps for x, y in zip(a, b))


def _same_face(face: Face, corners, uvs, normal=None):
    """Same corners with the same uvs, in the same turning order (so the same front)."""
    n = len(face.corners)
    if len(corners) != n:
        return False
    for shift in range(n):
        if all(_close(face.corners[i], corners[(i + shift) % n]) and _close(face.uvs[i], uvs[(i + shift) % n])
               for i in range(n)):
            return normal is None or mesh.dot(normal, face.normal()) > 0.999
    return False


def drawn_faces(built: geometry.BlockGeometry):
    """Every face the geometry draws, as (corners, uvs, normal or None, material)."""
    out = []
    bone = built.geometry["minecraft:geometry"][0]["bones"][0]
    for cube in bone.get("cubes", []):
        out += read_cube(cube)
    for corners, uvs in read_poly_mesh(bone.get("poly_mesh", {"polys": []})):
        out.append((corners, uvs, None, "*"))
    return out


def assert_reproduces(faces, built):
    drawn = drawn_faces(built)
    assert len(drawn) == len(faces)
    for face in faces:
        assert any(_same_face(face, c, u, n) for c, u, n, _ in drawn), f"not drawn: {face.corners} {face.uvs}"


# --------------------------------------------------------------------------
# Random faces
# --------------------------------------------------------------------------


def _random_rotation(rng):
    q = [rng.gauss(0, 1) for _ in range(4)]
    norm = math.sqrt(sum(c * c for c in q))
    w, x, y, z = (c / norm for c in q)
    return (
        (1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)),
        (2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)),
        (2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)),
    )


def _random_rect(rng, turned=True, texture="mcme:block/t"):
    """A rectangle face somewhere in the block, with a rectangle of texture in any of its 8 orientations."""
    w, h = rng.uniform(1, 10), rng.uniform(1, 10)
    local = [(0, 0, 0), (w, 0, 0), (w, h, 0), (0, h, 0)]  # counter-clockwise seen from +z
    m = _random_rotation(rng) if turned else mesh.IDENTITY
    centre = (rng.uniform(4, 12), rng.uniform(4, 12), rng.uniform(4, 12))
    corners = tuple(mesh.add(mesh.mat_vec(m, p), centre) for p in local)
    u0, v0 = rng.uniform(0, 8), rng.uniform(0, 8)
    du, dv = rng.uniform(1, 8), rng.uniform(1, 8)
    rect = [(u0, v0 + dv), (u0 + du, v0 + dv), (u0 + du, v0), (u0, v0)]
    if rng.random() < 0.5:
        rect = [(2 * u0 + du - u, v) for u, v in rect]  # mirrored
    shift = rng.randrange(4)
    uvs = tuple(rect[(i + shift) % 4] for i in range(4))
    return Face(corners=corners, uvs=uvs, texture=texture)


@pytest.mark.parametrize("seed", range(40))
def test_a_turned_textured_rectangle_comes_back_exactly(seed):
    rng = random.Random(seed)
    faces = [_random_rect(rng) for _ in range(6)]
    built = geometry.build(faces, mode="hybrid", oversize="keep")
    assert not built.uses_poly_mesh
    assert_reproduces(faces, built)


@pytest.mark.parametrize("seed", range(20))
def test_an_axis_aligned_rectangle_needs_no_rotation(seed):
    rng = random.Random(1000 + seed)
    face = _random_rect(rng, turned=False)
    built = geometry.build([face], mode="hybrid", oversize="keep")
    cube = built.geometry["minecraft:geometry"][0]["bones"][0]["cubes"][0]
    assert "rotation" not in cube
    assert_reproduces([face], built)


@pytest.mark.parametrize("seed", range(20))
def test_with_a_poly_mesh_rectangles_are_turned_instead_of_their_uvs(seed):
    # The geometry is then 1.12.0, which has no uv_rotation
    rng = random.Random(2000 + seed)
    faces = [_random_rect(rng, turned=rng.random() < 0.5) for _ in range(4)]
    triangle = Face(corners=((1, 1, 1), (5, 1, 2), (3, 6, 1)), uvs=((0, 16), (16, 16), (8, 0)), texture="mcme:block/t")
    built = geometry.build(faces + [triangle], mode="hybrid", oversize="keep")
    assert built.uses_poly_mesh
    assert built.geometry["format_version"] == "1.12.0"
    assert "uv_rotation" not in str(built.geometry)
    assert_reproduces(faces + [triangle], built)


def test_euler_angles_give_back_the_rotation():
    rng = random.Random(7)
    for _ in range(200):
        m = _random_rotation(rng)
        x, y, z = geometry.euler_zyx(m)
        again = _rz_ry_rx(x, y, z)
        assert all(abs(m[i][j] - again[i][j]) < 1e-9 for i in range(3) for j in range(3))


# --------------------------------------------------------------------------
# JSON elements
# --------------------------------------------------------------------------

CUBE_ALL = {"from": [0, 0, 0], "to": [16, 16, 16], "faces": {d: {"texture": "#all"} for d in mesh.DIRECTIONS}}


def test_a_whole_plain_cube_is_bedrocks_full_block():
    faces = mesh.element_faces(CUBE_ALL, {"all": "minecraft:block/stone"}, True)
    built = geometry.build(faces)
    assert built.geometry is None
    assert set(built.full_block) == set(mesh.DIRECTIONS)
    assert built.materials()["*"].texture == "minecraft:block/stone"


@pytest.mark.parametrize("x,y", [(0, 90), (0, 180), (90, 0), (90, 90), (270, 180), (180, 270)])
@pytest.mark.parametrize("uvlock", [False, True])
def test_a_turned_element_stays_one_cube_on_the_grid(x, y, uvlock):
    element = {
        "from": [2, 0, 4],
        "to": [10, 6, 16],
        "faces": {d: {"texture": "#t", "uv": [1, 2, 9, 8], "rotation": 90 if d == "up" else 0} for d in mesh.DIRECTIONS},
    }
    faces = mesh.rotate_faces(mesh.element_faces(element, {"t": "mcme:block/t"}, True), x, y, uvlock)
    built = geometry.build(faces)
    cubes = built.geometry["minecraft:geometry"][0]["bones"][0]["cubes"]
    assert len(cubes) == 1 and "rotation" not in cubes[0]
    assert_reproduces(faces, built)


def test_an_element_rotation_becomes_the_cubes_rotation():
    element = {
        "from": [0.8, 0, 8],
        "to": [15.2, 16, 8],
        "rotation": {"origin": [8, 8, 8], "axis": "y", "angle": 45, "rescale": True},
        "faces": {"north": {"texture": "#cross"}, "south": {"texture": "#cross"}},
    }
    faces = mesh.element_faces(element, {"cross": "minecraft:block/poppy"}, False)
    built = geometry.build(faces)
    (cube,) = built.geometry["minecraft:geometry"][0]["bones"][0]["cubes"]
    assert cube["rotation"] == [0.0, -45.0, 0.0]
    assert_reproduces(faces, built)
    # rescale stretches the plane across the block's diagonal
    assert abs(cube["size"][0] - 14.4 * math.sqrt(2)) < 1e-3


def test_two_textures_get_two_material_instances():
    element = {"from": [0, 0, 0], "to": [16, 8, 16], "faces": {
        "up": {"texture": "#top"}, "down": {"texture": "#bottom"}, "north": {"texture": "#side"}}}
    faces = mesh.element_faces(element, {"top": "a:t", "bottom": "a:b", "side": "a:t"}, True)
    built = geometry.build(faces)
    names = built.materials()
    assert {m.texture for m in names.values()} == {"a:t", "a:b"}
    for corners, uvs, normal, name in drawn_faces(built):
        face = next(f for f in faces if _same_face(f, corners, uvs, normal))
        assert names[name].texture == face.texture


# --------------------------------------------------------------------------
# Faces that aren't rectangles
# --------------------------------------------------------------------------

TRIANGLE = Face(corners=((0, 0, 8), (16, 0, 8), (8, 16, 8)), uvs=((0, 16), (16, 16), (8, 0)), texture="mcme:block/t")


def test_hybrid_puts_a_triangle_in_the_poly_mesh_as_a_quad():
    built = geometry.build([TRIANGLE])
    poly_mesh = built.geometry["minecraft:geometry"][0]["bones"][0]["poly_mesh"]
    (poly,) = poly_mesh["polys"]
    assert len(poly) == 4 and poly[3] == poly[0]
    assert poly_mesh["normalized_uvs"] is True
    assert_reproduces([TRIANGLE], built)
    # Normals mirror x like positions: this triangle faces south (+z), still +z in the file
    assert poly_mesh["normals"] == [[0.0, 0.0, 1.0]]


def test_two_triangles_of_one_rectangle_become_one_cube_face():
    a = Face(corners=((0, 0, 8), (16, 0, 8), (16, 16, 8)), uvs=((0, 16), (16, 16), (16, 0)), texture="mcme:block/t")
    b = Face(corners=((0, 0, 8), (16, 16, 8), (0, 16, 8)), uvs=((0, 16), (16, 0), (0, 0)), texture="mcme:block/t")
    built = geometry.build([a, b])
    assert not built.uses_poly_mesh
    (corners, uvs, normal, _), = drawn_faces(built)
    quad = Face(corners=((0, 0, 8), (16, 0, 8), (16, 16, 8), (0, 16, 8)), uvs=((0, 16), (16, 16), (16, 0), (0, 0)), texture="x")
    assert _same_face(quad, corners, uvs, normal)


def test_cubes_mode_draws_the_rectangle_around_a_triangle():
    built = geometry.build([TRIANGLE], mode="cubes")
    assert not built.uses_poly_mesh and built.approximated == 1
    (corners, _, normal, _), = drawn_faces(built)
    xs, ys = sorted(c[0] for c in corners), sorted(c[1] for c in corners)
    assert _close((xs[0], xs[-1], ys[0], ys[-1]), (0, 16, 0, 16))
    assert normal[2] > 0.999


def test_a_triangle_with_a_sheared_texture_still_becomes_a_textured_rectangle():
    sheared = Face(corners=((0, 0, 8), (16, 0, 8), (8, 16, 8)), uvs=((0, 16), (16, 12), (4, 0)), texture="mcme:block/t")
    built = geometry.build([sheared], mode="cubes")
    (corners, uvs, normal, _), = drawn_faces(built)
    assert normal[2] > 0.999
    us, vs = sorted(u for u, _ in uvs), sorted(v for _, v in uvs)
    assert _close((us[0], us[-1], vs[0], vs[-1]), (0, 16, 0, 16))


def test_polymesh_mode_puts_every_obj_face_in_the_poly_mesh():
    rect = _random_rect(random.Random(3))
    built = geometry.build([rect, TRIANGLE], mode="polymesh", oversize="keep")
    bone = built.geometry["minecraft:geometry"][0]["bones"][0]
    assert "cubes" not in bone and len(bone["poly_mesh"]["polys"]) == 2
    assert_reproduces([rect, TRIANGLE], built)


def test_a_second_texture_cant_join_the_poly_mesh():
    other = Face(corners=TRIANGLE.corners, uvs=TRIANGLE.uvs, texture="mcme:block/other")
    built = geometry.build([TRIANGLE, TRIANGLE, other])
    assert built.slots[0].texture == "mcme:block/t" and built.approximated == 1


# --------------------------------------------------------------------------
# Bedrock's size limit
# --------------------------------------------------------------------------


def _quad_at(x0, y0, z, size=4):
    return Face(corners=((x0, y0, z), (x0 + size, y0, z), (x0 + size, y0 + size, z), (x0, y0 + size, z)),
                uvs=((0, 16), (16, 16), (16, 0), (0, 0)), texture="mcme:block/t")


def test_geometry_beyond_thirty_pixels_is_kept_whole_by_default():
    # As Java draws an .obj far outside its block
    faces = [_quad_at(2, 2, 8), _quad_at(40, 2, 8)]
    built = geometry.build(faces)
    assert built.oversize and built.dropped == 0
    assert_reproduces(faces, built)


def test_oversize_polymesh_puts_the_whole_model_in_the_poly_mesh():
    faces = [_quad_at(2, 2, 8), _quad_at(40, 2, 8)]
    built = geometry.build(faces, oversize="polymesh")
    bone = built.geometry["minecraft:geometry"][0]["bones"][0]
    assert built.oversize and "cubes" not in bone and len(bone["poly_mesh"]["polys"]) == 2
    assert_reproduces(faces, built)
    # A model that fits keeps its cubes
    small = geometry.build([_quad_at(2, 2, 8)], oversize="polymesh")
    assert not small.uses_poly_mesh and not small.oversize


def test_clip_leaves_out_the_faces_beyond_thirty_pixels():
    inside = _quad_at(2, 2, 8)
    built = geometry.build([inside, _quad_at(40, 2, 8)], oversize="clip")
    assert built.dropped == 1
    assert_reproduces([inside], built)


def test_geometry_may_reach_fourteen_pixels_past_the_cell():
    edge = _quad_at(26, 2, 8)  # reaches x = 30: the window 0..30 holds it with the cell
    built = geometry.build([edge], oversize="clip")
    assert built.dropped == 0 and not built.oversize


# --------------------------------------------------------------------------
# The poly_mesh against a mesh Bedrock is known to draw
# --------------------------------------------------------------------------

# The example pack the conversion was designed against: a 1,000,000-polygon
# poly_mesh that Bedrock draws (on an entity). It isn't ours to copy into the
# repository, so the test reads it where it lies and is skipped elsewhere.
EXAMPLE = Path(os.environ.get(
    "MCME_POLYMESH_EXAMPLE",
    Path.home() / "Downloads" / "Armory (High Poly)" / "resource_packs" / "TheArmoryR" / "models" / "entity" / "armory_high_poly.geo.json",
))


def _winding_signs(poly_mesh, limit=None):
    """For each polygon: does its corner order turn the same way as its stored normal points?"""
    signs = []
    for poly in poly_mesh["polys"][:limit]:
        a, b, c = (poly_mesh["positions"][poly[i][0]] for i in range(3))
        n = poly_mesh["normals"][poly[0][1]]
        g = mesh.cross(mesh.sub(b, a), mesh.sub(c, a))
        if mesh.length(g) > 1e-9:
            signs.append(mesh.dot(g, n) > 0)
    return signs


@pytest.mark.skipif(not EXAMPLE.is_file(), reason="the example pack isn't on this machine")
def test_our_poly_mesh_is_written_like_the_example_bedrock_draws():
    with open(EXAMPLE, "rb") as f:
        example = json.load(f)["minecraft:geometry"][0]["bones"][0]["poly_mesh"]

    triangles = [
        Face(corners=((0, 0, 8), (16, 0, 8), (8, 16, 8)), uvs=((0, 16), (16, 16), (8, 0)), texture="mcme:block/t"),
        Face(corners=((2, 1, 3), (9, 4, 12), (5, 15, 6)), uvs=((1, 15), (12, 9), (6, 2)), texture="mcme:block/t"),
        Face(corners=((14, 2, 2), (3, 2, 14), (3, 9, 2)), uvs=((0, 0), (16, 0), (8, 16)), texture="mcme:block/t"),
    ]
    ours = geometry.build(triangles).geometry["minecraft:geometry"][0]["bones"][0]["poly_mesh"]

    assert set(ours) <= set(example)
    assert ours["normalized_uvs"] == example["normalized_uvs"] is True
    # Every polygon is four corners, a triangle repeating its first
    assert all(len(p) == 4 and p[3] == p[0] for p in example["polys"][:10000])
    assert all(len(p) == 4 and p[3] == p[0] for p in ours["polys"])
    # Corners turn against the stored normal in the file, as the mirrored x
    # makes them, in the large majority of the example's polygons and in all of ours
    example_signs = _winding_signs(example)
    assert sum(example_signs) < 0.35 * len(example_signs)
    assert not any(_winding_signs(ours))
    assert all(0 <= u <= 1 and 0 <= v <= 1 for u, v in ours["uvs"])
