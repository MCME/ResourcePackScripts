import json
from pathlib import Path

import cropPlanes
from PIL import Image

PARENT = {
    "elements": [
        {
            "from": [-16, -16, 8],
            "to": [32, 32, 8],
            "shade": False,
            "rotation": {"angle": -22.5, "axis": "y", "origin": [8, 0, 8]},
            "faces": {
                "north": {"uv": [16, 0, 0, 16], "texture": "#1"},
                "south": {"uv": [0, 0, 16, 16], "texture": "#1"},
            },
        },
        {
            "from": [8, -16, -16],
            "to": [8, 32, 32],
            "faces": {"east": {"uv": [16, 0, 0, 16], "texture": "#2"}, "west": {"uv": [0, 0, 16, 16], "texture": "#2"}},
        },
    ]
}


def _texture(path: Path, box=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGBA", (48, 48), (0, 0, 0, 0))
    if box:
        for x in range(box[0], box[2]):
            for y in range(box[1], box[3]):
                image.putpixel((x, y), (40, 160, 40, 255))
    image.save(path)


def _pack(tmp_path: Path):
    models = tmp_path / "assets" / "minecraft" / "models" / "block"
    models.mkdir(parents=True)
    (models / "3x3x3vegetation_test.json").write_text(json.dumps(PARENT))
    (models / "grass.json").write_text(
        json.dumps({"parent": "block/3x3x3vegetation_test", "textures": {"1": "block/blades", "2": "block/empty"}})
    )
    textures = tmp_path / "assets" / "minecraft" / "textures" / "block"
    # visible texels in columns 16-31, rows 24-47: the plane's middle third, bottom half
    _texture(textures / "blades.png", (16, 24, 32, 48))
    _texture(textures / "empty.png")
    return models / "grass.json"


def test_crops_to_the_visible_texels_and_drops_empty_planes(tmp_path: Path):
    model = _pack(tmp_path)
    changed = cropPlanes.crop_pack(tmp_path, "block/3x3x3vegetation", 0, write=True)
    assert changed[model][:2] == (2, 1)

    (element,) = json.loads(model.read_text())["elements"]
    # 48 texels over 48 units: a texel is a unit, and v runs down from the top
    assert element["from"] == [0, -16, 8] and element["to"] == [16, 8, 8]
    assert element["faces"]["south"]["uv"] == [5.3333, 8, 10.6667, 16]
    assert element["faces"]["north"]["uv"] == [10.6667, 8, 5.3333, 16]
    # everything but the planes is the parent's
    assert element["rotation"] == PARENT["elements"][0]["rotation"] and element["shade"] is False


def test_margin_keeps_aligned_texels_around(tmp_path: Path):
    model = _pack(tmp_path)
    cropPlanes.crop_pack(tmp_path, "block/3x3x3vegetation", 8, write=True)
    (element,) = json.loads(model.read_text())["elements"]
    # columns 8-40, rows 16-48
    assert element["from"] == [-8, -16, 8] and element["to"] == [24, 16, 8]


def test_second_run_changes_nothing(tmp_path: Path):
    _pack(tmp_path)
    assert cropPlanes.crop_pack(tmp_path, "block/3x3x3vegetation", 4, write=True)
    assert cropPlanes.crop_pack(tmp_path, "block/3x3x3vegetation", 4, write=False) == {}


def test_leaves_planes_it_cannot_map(tmp_path: Path):
    element = dict(PARENT["elements"][0], faces={"north": {"uv": [16, 0, 0, 16], "texture": "#1", "rotation": 90}})
    assert cropPlanes.crop_element(element, {"1": "block/blades"}, cropPlanes.Alpha(tmp_path), 0) is element
    # a texture the pack doesn't have (the game's own) is left as it is too
    assert cropPlanes.crop_element(PARENT["elements"][0], {"1": "block/vanilla"}, cropPlanes.Alpha(tmp_path), 0) is PARENT["elements"][0]
