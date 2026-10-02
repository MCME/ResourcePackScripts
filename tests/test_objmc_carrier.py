"""Unit tests for objmc's carrier element placement."""

import pytest

import objmc

# objmc's default offset puts OBJ (0, 0, 0) on the block's lower north-west corner.
OFFSET = (-0.5, 0.0, -0.5)


def _corners(direction, rotation, lo, hi):
    """The carrier face's corners where the client puts them, in its order."""
    m = objmc.rotation_matrix(rotation or {"x": 0.0, "y": 0.0, "z": 0.0})
    return [
        objmc.rotate(m, [(lo, hi)[pick[a]][a] for a in range(3)])
        for pick in objmc.FACE_CORNERS[direction]
    ]


def _face(n):
    return [[i, 0] for i in range(n)]


# =========================================================================
# carrier()
# =========================================================================


def test_carrier_sits_at_the_real_face_in_the_block():
    # An up face, wound anticlockwise seen from above.
    positions = [[0.25, 0.5, 0.75], [0.75, 0.5, 0.75], [0.75, 0.5, 0.25], [0.25, 0.5, 0.25]]

    (direction, rotation, lo, hi), _ = objmc.carrier(_face(4), positions, 1.0, OFFSET)

    assert direction == "up"
    assert [lo[0], lo[2], hi[0], hi[2]] == pytest.approx([4, 4, 12, 12], abs=0.01)
    assert lo[1] == pytest.approx(8, abs=0.02)


def test_carrier_tilts_a_sideways_face_along_an_axis():
    # A south face, wound anticlockwise seen from the south.
    positions = [[0.25, 0.25, 0.5], [0.75, 0.25, 0.5], [0.75, 0.75, 0.5], [0.25, 0.75, 0.5]]

    (direction, rotation, lo, hi), _ = objmc.carrier(_face(4), positions, 1.0, OFFSET)

    # Not flat across the south axis, or the client lights it from the block
    # to the south - black when that is solid.
    assert direction == "south"
    zs = [c[2] for c in _corners(direction, rotation, lo, hi)]
    assert max(zs) > min(zs)


def test_carrier_leaves_an_upward_face_flat():
    # Tilted 30 degrees, still facing mostly up.
    positions = [[0.25, 0.4, 0.75], [0.75, 0.4, 0.75], [0.75, 0.7, 0.25], [0.25, 0.7, 0.25]]

    (direction, rotation, lo, hi), _ = objmc.carrier(_face(4), positions, 1.0, OFFSET)

    # Flat and unrotated, so the client occludes and lights it from above.
    assert direction == "up"
    assert rotation is None
    assert lo[1] == hi[1]


def test_carrier_turns_the_vertices_onto_the_corners_they_are_occluded_at():
    positions = [[0.25, 0.5, 0.75], [0.75, 0.5, 0.75], [0.75, 0.5, 0.25], [0.25, 0.5, 0.25]]

    element, order = objmc.carrier(_face(4), positions, 1.0, OFFSET)

    for vertex, corner in zip(order, _corners(*element)):
        placed = objmc.block_position(positions[vertex[0]], 1.0, OFFSET)
        assert [placed[0], placed[2]] == pytest.approx([corner[0], corner[2]], abs=0.05)


def test_carrier_keeps_the_winding_of_the_face():
    positions = [[0.25, 0.5, 0.75], [0.75, 0.5, 0.75], [0.75, 0.5, 0.25], [0.25, 0.5, 0.25]]

    _, order = objmc.carrier(_face(4), positions, 1.0, OFFSET)

    start = [v[0] for v in order].index(0)
    assert [v[0] for v in order[start:] + order[:start]] == [0, 1, 2, 3]


def test_carrier_turns_a_triangle_without_losing_a_vertex():
    positions = [[0.75, 0.5, 0.25], [0.25, 0.5, 0.75], [0.75, 0.5, 0.75]]

    _, order = objmc.carrier(_face(3), positions, 1.0, OFFSET)

    assert sorted(v[0] for v in order) == [0, 1, 2]


def test_carrier_stays_inside_the_block_for_a_face_reaching_past_it():
    # A diagonal plane spanning three blocks.
    positions = [[-1.0, -1.0, 0.5], [2.0, -1.0, 0.5], [2.0, 2.0, 0.4], [-1.0, 2.0, 0.4]]

    element, _ = objmc.carrier(_face(4), positions, 1.0, OFFSET)

    for corner in _corners(*element):
        for c in corner:
            assert objmc.CARRIER_MARGIN - 1e-9 <= c <= 16 - objmc.CARRIER_MARGIN + 1e-9


def test_carrier_gives_a_sliver_of_a_face_an_area():
    positions = [[0.5, 0.2, 0.5], [0.5, 0.2, 0.5], [0.5, 0.8, 0.5]]

    (direction, rotation, lo, hi), _ = objmc.carrier(_face(3), positions, 1.0, OFFSET)

    axis = "xyz".index(objmc.DIRECTION_AXIS[direction][0])
    for a in range(3):
        if a != axis:
            assert hi[a] - lo[a] >= objmc.CARRIER_MIN_SIZE - 1e-9


def test_carrier_centred_sits_at_the_block_centre(tmp_path):
    # A face reaching right to the block's edges.
    positions = [[0.0, 0.0, 0.5], [1.0, 0.0, 0.5], [1.0, 1.0, 0.4], [0.0, 1.0, 0.4]]

    element, _ = objmc.carrier(_face(4), positions, 1.0, OFFSET, centred=True)

    # No random block offset (at most 0.25 of a block, 4 pixels) can carry a
    # corner into another block, and the shader reads the offset back from it.
    for corner in _corners(*element):
        assert max(abs(c - 8) for c in corner) < 0.05

