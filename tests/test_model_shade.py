import json
from pathlib import Path

import model_shade
import pytest

GRASS = (
    "{\n"
    '\t"elements": [\n'
    "\t\t{\n"
    '\t\t\t"from": [0, 0, 8],\n'
    '\t\t\t"shade": false,\n'
    '\t\t\t"faces": {}\n'
    "\t\t},\n"
    "\t\t{\n"
    '\t\t\t"from": [8, 0, 0],\n'
    '\t\t\t"shade": false\n'
    "\t\t},\n"
    "\t\t{\n"
    '\t\t\t"from": [0, 0, 0],\n'
    '\t\t\t"faces": {}\n'
    "\t\t}\n"
    "\t]\n"
    "}\n"
)


def test_add_override_after_each_shade_false():
    fixed = model_shade.add_override(GRASS)
    assert fixed == GRASS.replace(
        '\t\t\t"shade": false,\n', '\t\t\t"shade": false,\n\t\t\t"shade_direction_override": "up",\n'
    ).replace('\t\t\t"shade": false\n', '\t\t\t"shade": false,\n\t\t\t"shade_direction_override": "up"\n')
    elements = json.loads(fixed)["elements"]
    assert [e.get("shade_direction_override") for e in elements] == ["up", "up", None]


def test_add_override_keeps_crlf():
    fixed = model_shade.add_override(GRASS.replace("\n", "\r\n"))
    assert "\n" not in fixed.replace("\r\n", "")
    assert model_shade.missing_override(fixed) == 0


def test_add_override_leaves_elements_that_have_it():
    once = model_shade.add_override(GRASS)
    assert model_shade.add_override(once) == once


def test_add_override_refuses_shade_false_not_on_its_own_line():
    with pytest.raises(model_shade.ModelShadeError):
        model_shade.add_override('{"elements": [{"shade": false, "faces": {}}]}')


def test_missing_override_counts_elements():
    assert model_shade.missing_override(GRASS) == 2
    assert model_shade.missing_override('{"parent": "block/cross"}') == 0
    assert model_shade.missing_override("not json") == 0


def test_check_and_fix_a_pack(tmp_path: Path):
    model = tmp_path / "assets" / "minecraft" / "models" / "block" / "grass.json"
    model.parent.mkdir(parents=True)
    model.write_bytes(b"\xef\xbb\xbf" + GRASS.encode())
    (tmp_path / "assets" / "minecraft" / "blockstates").mkdir(parents=True)
    (tmp_path / "assets" / "minecraft" / "blockstates" / "grass.json").write_text(GRASS)

    assert model_shade.check(tmp_path) == {model: 2}
    assert model_shade.fix(tmp_path) == {model: 2}
    assert model_shade.check(tmp_path) == {}
    # the BOM stays, and files outside models/ are left alone
    assert model.read_bytes().startswith(b"\xef\xbb\xbf")
    assert (tmp_path / "assets" / "minecraft" / "blockstates" / "grass.json").read_text() == GRASS
