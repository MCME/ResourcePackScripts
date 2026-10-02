"""Unit tests for objmc_merge: bakes sharing a texture, merged into one sprite."""

import json

from PIL import Image

import objmc
import objmc_merge
from objmc_decode import decode_model

QUAD_OBJ = """v 0 0 0
v 1 0 0
v 1 1 0
v 0 1 0
vt 0 0
vt 1 0
vt 1 1
vt 0 1
f 1/1 2/2 3/3 4/4
"""

TWO_QUADS_OBJ = QUAD_OBJ + """v 0 0 1
v 1 0 1
v 1 1 1
v 0 1 1
f 5/1 6/2 7/3 8/4
"""


def _texture(colour):
    image = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    for x in range(4, 12):
        image.putpixel((x, 6), colour)
    return image


def _bake(tmp_path, name, obj_text, texture):
    """objmc's bake and carriers for a model, written where the converter puts
    them; returns the carriers."""
    pack = tmp_path / "pack"
    (pack / "assets/mcme/textures/block").mkdir(parents=True, exist_ok=True)
    (pack / "assets/mcme/models/block").mkdir(parents=True, exist_ok=True)
    obj = tmp_path / f"{name}.obj"
    obj.write_text(obj_text)
    source = tmp_path / f"{name}_source.png"
    texture.save(source)
    carriers = tmp_path / f"{name}_carriers.json"
    objmc.objmc(str(obj), str(source), [str(carriers), str(pack / f"assets/mcme/textures/block/{name}.png")])
    with open(carriers) as f:
        data = json.load(f)
    data["textures"] = {"0": f"mcme:block/{name}", "particle": f"mcme:block/{name}"}
    return data


def _write(tmp_path, name, data):
    with open(tmp_path / f"pack/assets/mcme/models/block/{name}.json", "w") as f:
        json.dump(data, f)


def _read(tmp_path, name):
    with open(tmp_path / f"pack/assets/mcme/models/block/{name}.json") as f:
        return json.load(f)


def _image(tmp_path, identifier):
    path = identifier.split(":", 1)[1]
    with Image.open(tmp_path / f"pack/assets/mcme/textures/{path}.png") as image:
        return image.convert("RGBA")


def _decoded(tmp_path, name, elements=None):
    data = _read(tmp_path, name)
    return decode_model(_image(tmp_path, data["textures"]["0"]), elements or data["elements"])


# =========================================================================
# merge_shared_textures()
# =========================================================================


def test_merge_stores_a_shared_texture_once(tmp_path):
    leaves = _texture((40, 120, 30, 255))
    for name, obj in (("a", QUAD_OBJ), ("b", TWO_QUADS_OBJ)):
        _write(tmp_path, name, _bake(tmp_path, name, obj, leaves))
    _write(tmp_path, "c", _bake(tmp_path, "c", QUAD_OBJ, _texture((90, 60, 20, 255))))
    before = {name: _decoded(tmp_path, name) for name in "abc"}
    c_bake = (tmp_path / "pack/assets/mcme/textures/block/c.png").read_bytes()

    objmc_merge.merge_shared_textures(tmp_path / "pack", True, False)

    assert _read(tmp_path, "a")["textures"] == _read(tmp_path, "b")["textures"]
    assert sorted(p.name for p in (tmp_path / "pack/assets/mcme/textures/block").iterdir()) == ["a.png", "c.png"]
    assert (tmp_path / "pack/assets/mcme/textures/block/c.png").read_bytes() == c_bake
    assert {name: _decoded(tmp_path, name) for name in "abc"} == before


def test_merge_gives_each_model_its_own_copy_of_a_shared_parent(tmp_path):
    leaves = _texture((40, 120, 30, 255))
    parent = None
    for name in ("a", "b"):
        data = _bake(tmp_path, name, TWO_QUADS_OBJ, leaves)
        parent = {"elements": data.pop("elements")}
        data["parent"] = "mcme:block/leaves_parent"
        _write(tmp_path, name, data)
    _write(tmp_path, "leaves_parent", parent)
    before = {name: _decoded(tmp_path, name, parent["elements"]) for name in "ab"}

    objmc_merge.merge_shared_textures(tmp_path / "pack", True, False)

    for name in "ab":
        assert "parent" not in _read(tmp_path, name)
        assert _decoded(tmp_path, name) == before[name]
    assert not (tmp_path / "pack/assets/mcme/models/block/leaves_parent.json").exists()


def test_merge_leaves_a_flipbook_alone(tmp_path):
    leaves = _texture((40, 120, 30, 255))
    for name in "ab":
        _write(tmp_path, name, _bake(tmp_path, name, QUAD_OBJ, leaves))
    (tmp_path / "pack/assets/mcme/textures/block/b.png.mcmeta").write_text('{"animation": {}}')
    b_bake = (tmp_path / "pack/assets/mcme/textures/block/b.png").read_bytes()
    b_model = _read(tmp_path, "b")

    objmc_merge.merge_shared_textures(tmp_path / "pack", True, False)

    assert (tmp_path / "pack/assets/mcme/textures/block/b.png").read_bytes() == b_bake
    assert _read(tmp_path, "b") == b_model


def test_merge_splits_a_group_too_tall_for_one_sprite(tmp_path, monkeypatch):
    leaves = _texture((40, 120, 30, 255))
    for name in "abc":
        _write(tmp_path, name, _bake(tmp_path, name, TWO_QUADS_OBJ, leaves))
    before = {name: _decoded(tmp_path, name) for name in "abc"}
    # The texture block (16 rows padded to 48) and two models' blocks fit.
    monkeypatch.setattr(objmc_merge, "MAX_SPRITE_HEIGHT", 64)

    objmc_merge.merge_shared_textures(tmp_path / "pack", True, False)

    sprites = {_read(tmp_path, name)["textures"]["0"] for name in "abc"}
    assert len(sprites) == 2
    assert {name: _decoded(tmp_path, name) for name in "abc"} == before
