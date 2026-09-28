"""Unit tests for the path helpers in util."""

import util
from conftest import symlink_or_skip

# =========================================================================
# contained_path()
# =========================================================================


def test_contained_path_resolves_a_path_inside_the_root(tmp_path):
    assert (
        util.contained_path(tmp_path, "assets/mcme/models/lamp.json")
        == (tmp_path / "assets/mcme/models/lamp.json").resolve()
    )


def test_contained_path_allows_dot_dot_segments_that_stay_inside(tmp_path):
    assert (
        util.contained_path(tmp_path, "assets/mcme/../minecraft/models/stone.json")
        == (tmp_path / "assets/minecraft/models/stone.json").resolve()
    )


def test_contained_path_rejects_dot_dot_segments_leading_out(tmp_path):
    root = tmp_path / "pack"

    assert (
        util.contained_path(root, "assets/mcme/models/../../../../secret.json") is None
    )


def test_contained_path_rejects_an_absolute_path_elsewhere(tmp_path):
    root = tmp_path / "pack"

    assert util.contained_path(root, tmp_path / "secret.json") is None


def test_contained_path_rejects_a_symlink_leading_out(tmp_path):
    root = tmp_path / "pack"
    root.mkdir()
    secret = tmp_path / "secret.png"
    secret.write_bytes(b"host file")
    symlink_or_skip(root / "texture.png", secret)

    assert util.contained_path(root, "texture.png") is None


def test_contained_path_allows_a_symlink_that_stays_inside(tmp_path):
    root = tmp_path / "pack"
    real = root / "assets" / "real.png"
    real.parent.mkdir(parents=True)
    real.write_bytes(b"texture")
    symlink_or_skip(root / "alias.png", real)

    assert util.contained_path(root, "alias.png") == real.resolve()
