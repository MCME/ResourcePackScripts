"""Unit tests for objmc_conversion, with the objmc subprocess faked.

These cover our own logic either side of the objmc boundary - path resolution,
.objmeta handling, parent linking - and deliberately never run the real script,
so they are fast and need no objmc installed. The real script is pinned
separately in test_objmc_golden.py.
"""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import constants
import objmc_conversion
import pytest
from conftest import symlink_or_skip
from PIL import Image


# ---------- filesystem helpers ----------


def _write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def _write_text(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _sodium_model(input_path: Path, model_path: str, data):
    _write_json(
        input_path
        / constants.RELATIVE_SODIUM_MODELS_PATH
        / Path(model_path + constants.VANILLA_MODEL_EXTENSION),
        data,
    )


def _sodium_obj(input_path: Path, model_path: str, text: str = "# obj"):
    _write_text(
        input_path
        / constants.RELATIVE_SODIUM_MODELS_PATH
        / Path(model_path + constants.OBJ_MODEL_EXTENSION),
        text,
    )


def _sodium_mtl(input_path: Path, mtl_path: str, texture: str):
    _write_text(
        input_path
        / constants.RELATIVE_SODIUM_MODELS_PATH
        / Path(mtl_path + constants.MTL_EXTENSION),
        f"newmtl foo\nmap_Kd {texture}\n",
    )


def _sodium_texture(input_path: Path, texture_path: str, content: bytes = b"\x89PNG"):
    p = (
        input_path
        / constants.RELATIVE_SODIUM_TEXTURES_PATH
        / Path(texture_path + constants.TEXTURE_EXTENSION)
    )
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)


# ---------- fake objmc subprocess ----------


def _make_fake_objmc(default_output_model=None):
    """Returns a subprocess.run replacement that writes a fake output model JSON
    at whatever path is passed via `--out`, alongside a small but real PNG as
    the baked texture - the conversion reads that texture's size to decide
    whether two bakes may share a parent. Returns a completed-process mock."""

    default_output_model = default_output_model or {
        "textures": {"0": "placeholder", "particle": "placeholder"},
        "elements": [{"faces": {"north": {"tintindex": 0, "uv": [0, 0, 1, 1]}}}],
        "display": {"gui": {}},
        "gui_light": "front",
    }

    def _fake(cmd, check=False, stdout=None, stderr=None):
        # cmd is the argv: [sys.executable, objmc, '--objs', ..., '--out', MODEL, TEX, ...]
        out_idx = cmd.index("--out")
        model_out = Path(cmd[out_idx + 1])
        tex_out = Path(cmd[out_idx + 2])
        model_out.parent.mkdir(parents=True, exist_ok=True)
        tex_out.parent.mkdir(parents=True, exist_ok=True)
        model_out.write_text(json.dumps(default_output_model))
        Image.new("RGBA", (8, 8)).save(tex_out)
        result = MagicMock()
        result.returncode = 0
        result.stdout = b""
        result.stderr = b""
        return result

    return _fake


# =========================================================================
# convert_sodium_model()
# =========================================================================


def _setup_basic_convert_inputs(
    tmp_path,
    model_path="props/lamp",
    model_content=None,
    extra_mtl_texture="mcme:props/lamp",
):
    """Lay out the minimum files the conversion needs: model json stub, obj file, mtl file."""
    input_path = tmp_path / "in"
    output_path = tmp_path / "out"
    objmc_path = tmp_path / "objmc.py"
    objmc_path.write_text("# fake")

    if model_content is None:
        model_content = {"model": f"mcme:models/{model_path}.obj"}
    _sodium_model(input_path, model_path, model_content)
    _sodium_obj(input_path, model_path)
    _sodium_mtl(input_path, model_path, extra_mtl_texture)
    _sodium_texture(input_path, model_path)
    return input_path, output_path, objmc_path


def test_convert_model_missing_input_file_returns_early(tmp_path, capsys):
    input_path = tmp_path / "in"
    output_path = tmp_path / "out"
    objmc_path = tmp_path / "objmc.py"

    with patch.object(subprocess, "run") as mock_run:
        objmc_conversion.convert_sodium_model(
            input_path,
            output_path,
            "props/absent",
            None,
            objmc_path,
            False,
            False,
        )
    mock_run.assert_not_called()
    assert "WARNING" in capsys.readouterr().out


def test_convert_model_happy_path_no_rotation(tmp_path):
    input_path, output_path, objmc_path = _setup_basic_convert_inputs(tmp_path)

    with patch.object(subprocess, "run", side_effect=_make_fake_objmc()):
        objmc_conversion.convert_sodium_model(
            input_path,
            output_path,
            "props/lamp",
            None,
            objmc_path,
            False,
            False,
        )

    out_model = output_path / constants.RELATIVE_SODIUM_MODELS_PATH / "props/lamp.json"
    assert out_model.exists()
    data = json.loads(out_model.read_text())
    # the conversion rewrites texture refs to mcme:<output_texture_path>
    assert data["textures"]["0"] == "mcme:props/lamp"
    assert data["textures"]["particle"] == "mcme:props/lamp"
    # display + gui_light get stripped
    assert "display" not in data
    assert "gui_light" not in data
    # remove_tintindex clears tintindex on faces
    for element in data.get("elements", []):
        for face in element.get("faces", {}).values():
            assert "tintindex" not in face
    # lamp.obj is not named as a parent, so the model keeps its own geometry
    # and is never grouped for sharing
    assert objmc_conversion.converted_models == {}


def test_convert_model_rotation_creates_and_cleans_rotated_obj(tmp_path):
    input_path, output_path, objmc_path = _setup_basic_convert_inputs(tmp_path)

    with (
        patch.object(subprocess, "run", side_effect=_make_fake_objmc()),
        patch.object(objmc_conversion.rotate_obj, "rotate_obj_file") as mock_rotate,
    ):
        # rotate_obj_file must actually create the rotated file so the pipeline can
        # continue and the cleanup step at the end can unlink it.
        def _fake_rotate(src, dst, axis, angle):
            Path(dst).write_text("# rotated obj")

        mock_rotate.side_effect = _fake_rotate

        objmc_conversion.convert_sodium_model(
            input_path,
            output_path,
            "props/lamp",
            ("y", 90),
            objmc_path,
            False,
            False,
        )

    mock_rotate.assert_called_once()
    _, dst, axis, angle = mock_rotate.call_args.args
    assert axis == "y"
    assert angle == -90  # the conversion negates the angle
    # The rotated .obj should have been cleaned up
    assert not Path(dst).exists()

    out_model = (
        output_path / constants.RELATIVE_SODIUM_MODELS_PATH / "props/lamp_y_90.json"
    )
    assert out_model.exists()


def test_convert_model_shared_parent_extraction_on_second_call(tmp_path):
    """When a second model reads the same parent .obj, the second conversion
    turns both resulting model files into children of a shared *_parent file."""
    parent_obj = {"model": "mcme:models/props/lamp_parent.obj"}
    input_path, output_path, objmc_path = _setup_basic_convert_inputs(
        tmp_path, model_content=parent_obj
    )
    _sodium_obj(input_path, "props/lamp_parent")
    # a differently named model reading the same .obj, baked from a texture of
    # the same size - the two conditions for sharing geometry
    _sodium_model(input_path, "props/lamp_red", parent_obj)
    _sodium_mtl(input_path, "props/lamp_red", "mcme:props/lamp")

    with patch.object(subprocess, "run", side_effect=_make_fake_objmc()):
        for model_path in ("props/lamp", "props/lamp_red"):
            objmc_conversion.convert_sodium_model(
                input_path,
                output_path,
                model_path,
                None,
                objmc_path,
                False,
                False,
            )

    models = output_path / constants.RELATIVE_SODIUM_MODELS_PATH
    parent_model = models / (
        "props/lamp" + constants.PARENT_SUFFIX + constants.VANILLA_MODEL_EXTENSION
    )
    assert parent_model.exists()

    # Both models should now be children pointing at the parent
    for child in ("props/lamp", "props/lamp_red"):
        child_data = json.loads(
            (models / (child + constants.VANILLA_MODEL_EXTENSION)).read_text()
        )
        assert (
            child_data["parent"]
            == f"{constants.MCME_NAMESPACE}:props/lamp{constants.PARENT_SUFFIX}"
        )
        assert "elements" not in child_data

    # The parent should carry the shape but no textures
    parent_data = json.loads(parent_model.read_text())
    assert "textures" not in parent_data
    assert "elements" in parent_data

    # And the group should be marked as split out into its own file
    assert objmc_conversion.converted_models["props/lamp_parent"].file is None


# =========================================================================
# paths leading outside the pack
# =========================================================================
#
# Every path the conversion touches is built from pack content - the model
# identifier, the model json, the .objmeta and the .mtl - so a "../" segment or
# an absolute path in any of them could aim objmc at any file on the machine.
# The input and output packs sit side by side in tmp_path, so four ".."
# segments up from a pack's assets/mcme/<kind> folder land in tmp_path itself.


def _objmeta_file(input_path: Path, model_path: str) -> Path:
    return (
        input_path
        / constants.RELATIVE_SODIUM_MODELS_PATH
        / Path(model_path + constants.OBJMETA_EXTENSION)
    )


def _convert(input_path, output_path, objmc_path, model_path="props/lamp"):
    """Converts with objmc faked, returning the fake so a test can see if it ran."""
    with patch.object(subprocess, "run", side_effect=_make_fake_objmc()) as run:
        objmc_conversion.convert_sodium_model(
            input_path, output_path, model_path, None, objmc_path, False, False
        )
    return run


def _assert_skipped_as_outside_the_pack(run, capsys):
    run.assert_not_called()
    out = capsys.readouterr().out
    assert "WARNING" in out
    assert "outside the pack" in out


def test_convert_model_skips_a_model_path_leading_outside_the_pack(tmp_path, capsys):
    input_path, output_path, objmc_path = _setup_basic_convert_inputs(tmp_path)
    # the model identifier comes from a blockstate or item definition
    _write_json(
        tmp_path / "elsewhere.json",
        {
            "model": "mcme:models/props/lamp.obj",
            "mtl_override": "mcme:models/props/lamp.mtl",
        },
    )

    run = _convert(
        input_path, output_path, objmc_path, model_path="../../../../elsewhere"
    )

    _assert_skipped_as_outside_the_pack(run, capsys)


def test_convert_model_skips_an_obj_leading_outside_the_pack(tmp_path, capsys):
    input_path, output_path, objmc_path = _setup_basic_convert_inputs(
        tmp_path, model_content={"model": "mcme:models/../../../../elsewhere.obj"}
    )
    _write_text(tmp_path / "elsewhere.obj", "# obj")

    run = _convert(input_path, output_path, objmc_path)

    _assert_skipped_as_outside_the_pack(run, capsys)


def test_convert_model_skips_an_mtl_override_leading_outside_the_pack(tmp_path, capsys):
    input_path, output_path, objmc_path = _setup_basic_convert_inputs(
        tmp_path,
        model_content={
            "model": "mcme:models/props/lamp.obj",
            "mtl_override": "mcme:models/../../../../elsewhere.mtl",
        },
    )
    _write_text(tmp_path / "elsewhere.mtl", "map_Kd mcme:props/lamp\n")

    run = _convert(input_path, output_path, objmc_path)

    _assert_skipped_as_outside_the_pack(run, capsys)


def test_convert_model_skips_an_objmeta_texture_leading_outside_the_pack(
    tmp_path, capsys
):
    input_path, output_path, objmc_path = _setup_basic_convert_inputs(tmp_path)
    _write_text(_objmeta_file(input_path, "props/lamp"), "texture: ../../../../secret\n")
    (tmp_path / "secret.png").write_bytes(b"host file")

    run = _convert(input_path, output_path, objmc_path)

    _assert_skipped_as_outside_the_pack(run, capsys)


def test_convert_model_skips_an_mtl_texture_at_an_absolute_path(tmp_path, capsys):
    (tmp_path / "secret.png").write_bytes(b"host file")
    input_path, output_path, objmc_path = _setup_basic_convert_inputs(
        tmp_path, extra_mtl_texture=(tmp_path / "secret").as_posix()
    )

    run = _convert(input_path, output_path, objmc_path)

    _assert_skipped_as_outside_the_pack(run, capsys)


def test_convert_model_skips_an_output_texture_leading_outside_the_pack(
    tmp_path, capsys
):
    input_path, output_path, objmc_path = _setup_basic_convert_inputs(tmp_path)
    _write_text(
        _objmeta_file(input_path, "props/lamp"), "output_texture: ../../../../escaped\n"
    )

    run = _convert(input_path, output_path, objmc_path)

    _assert_skipped_as_outside_the_pack(run, capsys)
    assert not (tmp_path / "escaped.png").exists()


def test_convert_model_skips_a_shared_parent_leading_outside_the_pack(
    tmp_path, capsys
):
    """A shared parent is named after its .obj's path. A folder symlink in the
    input pack can put that .obj deeper there than the same text reaches in the
    output, which has no such link - so the path checks out in the input and
    still climbs out of the output. On Linux that stopped the whole run."""
    parent_obj = {"model": "mcme:models/deep/../../../../../x_parent.obj"}
    input_path, output_path, objmc_path = _setup_basic_convert_inputs(
        tmp_path, model_content=parent_obj
    )
    models = input_path / constants.RELATIVE_SODIUM_MODELS_PATH
    (models / "a/b/c/d/e").mkdir(parents=True)
    symlink_or_skip(models / "deep", models / "a/b/c/d/e")
    _sodium_obj(input_path, "x_parent")
    _sodium_model(input_path, "props/lamp_red", parent_obj)
    _sodium_mtl(input_path, "props/lamp_red", "mcme:props/lamp")

    with patch.object(subprocess, "run", side_effect=_make_fake_objmc()):
        for model_path in ("props/lamp", "props/lamp_red"):
            objmc_conversion.convert_sodium_model(
                input_path, output_path, model_path, None, objmc_path, False, False
            )

    assert not (tmp_path / "x_parent.json").exists()
    out = capsys.readouterr().out
    assert "WARNING" in out
    assert "outside the pack" in out


# =========================================================================
# the rotated .obj
# =========================================================================


def _snapshot(root: Path) -> dict:
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in root.rglob("*")
        if p.is_file()
    }


def test_convert_model_rotation_leaves_the_input_pack_untouched(tmp_path):
    """The rotated .obj objmc reads used to be written next to the source .obj
    and deleted afterwards - taking with it any real file that had its name."""
    input_path, output_path, objmc_path = _setup_basic_convert_inputs(tmp_path)
    _sodium_obj(input_path, "props/lamp_y_90", "# a real, committed model")
    before = _snapshot(input_path)

    with patch.object(subprocess, "run", side_effect=_make_fake_objmc()) as run:
        objmc_conversion.convert_sodium_model(
            input_path, output_path, "props/lamp", ("y", 90), objmc_path, False, False
        )

    assert _snapshot(input_path) == before
    argv = run.call_args.args[0]
    rotated_obj = Path(argv[argv.index("--obj") + 1])
    assert not rotated_obj.resolve().is_relative_to(input_path.resolve())


# =========================================================================
# flipbook textures
# =========================================================================

REAL_OBJMC = Path(__file__).resolve().parent.parent / "generateVanilla" / "objmc.py"

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


@pytest.mark.parametrize(
    "animation, sheet, expected",
    [
        ({}, (16, 64), (16, 16)),
        ({"height": 8}, (16, 64), (16, 8)),
        ({"width": 8, "height": 8}, (16, 64), (8, 8)),
        # The frame list never changes the cut, even when it lists more frames
        # than square frames give - the client shows square frames regardless.
        ({"frames": list(range(16))}, (48, 384), (48, 48)),
        ({"frames": [0, 1, 0]}, (48, 384), (48, 48)),
    ],
)
def test_flipbook_frame_size(animation, sheet, expected):
    assert objmc_conversion._flipbook_frame_size(animation, *sheet) == expected


@pytest.mark.parametrize("mipmap", [0, 1, 2, 4])
def test_bake_texture_rows_keep_mip_blocks_clear_of_data(mipmap):
    import objmc

    for start in range(3, 40):
        for texture_height in (1, 7, 8, 16, 24, 48):
            padding_top, top, data_top = objmc_conversion._bake_texture_rows(
                start, texture_height, mipmap
            )
            # The converter decodes the same layout objmc encodes.
            assert (top, data_top) == objmc.texture_layout(start, texture_height, mipmap)
            assert padding_top == start <= top
            assert top + texture_height <= data_top
            # Every block a mip level up to `mipmap` reads texture rows from
            # holds nothing but texture and its padding.
            for level in range(1, mipmap + 1):
                block = 1 << level
                first_block = top // block * block
                last_block_end = -(-(top + texture_height) // block) * block
                assert start <= first_block and last_block_end <= data_top


def test_convert_model_flipbook_drops_frames_past_the_sheet(tmp_path, capsys):
    from PIL import Image

    input_path, output_path, _ = _setup_basic_convert_inputs(tmp_path)
    _sodium_obj(input_path, "props/lamp", QUAD_OBJ)
    texture = input_path / constants.RELATIVE_SODIUM_TEXTURES_PATH / "props/lamp.png"
    Image.new("RGBA", (8, 16), (255, 0, 0, 255)).save(texture)
    _write_json(
        Path(str(texture) + ".mcmeta"),
        {"animation": {"frames": [0, {"index": 1, "time": 2}, 2, {"index": 3}]}},
    )

    objmc_conversion.convert_sodium_model(
        input_path, output_path, "props/lamp", None, REAL_OBJMC, False, False
    )

    out_texture = output_path / constants.RELATIVE_SODIUM_TEXTURES_PATH / "props/lamp.png"
    mcmeta = json.loads(Path(str(out_texture) + ".mcmeta").read_text())
    # Two square 8x8 frames: indices 2 and 3 do not exist.
    assert mcmeta["animation"]["frames"] == [0, {"index": 1, "time": 2}]
    assert Image.open(out_texture).height == 2 * mcmeta["animation"]["height"]
    assert "dropping them" in capsys.readouterr().out


def test_convert_model_flipbook_bakes_each_frame(tmp_path, monkeypatch):
    from PIL import Image

    # The texture rows asserted below are for 2 mip levels.
    monkeypatch.setattr(constants, "OBJMC_MIPMAP_LEVELS", 2)

    input_path, output_path, _ = _setup_basic_convert_inputs(tmp_path)
    _sodium_obj(input_path, "props/lamp", QUAD_OBJ)
    texture = input_path / constants.RELATIVE_SODIUM_TEXTURES_PATH / "props/lamp.png"
    colours = [(255, 0, 0, 255), (0, 255, 0, 255), (0, 0, 255, 128)]
    sheet = Image.new("RGBA", (8, 8 * len(colours)))
    for i, colour in enumerate(colours):
        sheet.paste(colour, (0, i * 8, 8, (i + 1) * 8))
    sheet.putpixel((0, 0), (1, 2, 3, 255))  # tells the texture's orientation apart
    sheet.save(texture)
    _write_json(
        Path(str(texture) + ".mcmeta"),
        {"animation": {"frametime": 3, "interpolate": True}},
    )

    objmc_conversion.convert_sodium_model(
        input_path, output_path, "props/lamp", None, REAL_OBJMC, False, False
    )

    out_texture = output_path / constants.RELATIVE_SODIUM_TEXTURES_PATH / "props/lamp.png"
    mcmeta = json.loads(Path(str(out_texture) + ".mcmeta").read_text())
    baked = Image.open(out_texture).convert("RGBA")
    frame_height = mcmeta["animation"]["height"]
    assert mcmeta["animation"] == {
        "frametime": 3,
        "interpolate": False,
        "width": 8,
        "height": frame_height,
    }
    assert baked.size == (8, frame_height * len(colours))

    frames = [
        baked.crop((0, i * frame_height, 8, (i + 1) * frame_height))
        for i in range(len(colours))
    ]
    # 1 face on an 8 wide texture: 2 header rows + 1 uv row, then mipmap padding
    # to the next 4-row boundary at least 4 rows on (8), the texture, and
    # padding to 4 rows past the boundary after it (20), where the data starts.
    padding_top, texture_rows, data_top = 3, (8, 16), 20
    for i, frame in enumerate(frames):
        source = sheet.crop((0, i * 8, 8, (i + 1) * 8)).transpose(Image.FLIP_TOP_BOTTOM)
        assert frame.crop((0, texture_rows[0], 8, texture_rows[1])).tobytes() == source.tobytes()
        first_row, last_row = source.crop((0, 0, 8, 1)), source.crop((0, 7, 8, 8))
        for y in range(padding_top, texture_rows[0]):
            assert frame.crop((0, y, 8, y + 1)).tobytes() == first_row.tobytes()
        for y in range(texture_rows[1], data_top):
            assert frame.crop((0, y, 8, y + 1)).tobytes() == last_row.tobytes()
        for rows in ((0, padding_top), (data_top, frame_height)):
            box = (0, rows[0], 8, rows[1])
            assert frame.crop(box).tobytes() == frames[0].crop(box).tobytes()


@pytest.mark.parametrize(
    "alphas, translucent",
    [
        ((255,), False),  # opaque
        ((0, 255), False),  # cutout: the shader sharpens its edges
        ((0, 128, 255), True),  # partly transparent texels: left alone
    ],
)
def test_objmc_flags_textures_with_translucent_texels(tmp_path, alphas, translucent):
    import objmc

    obj = tmp_path / "quad.obj"
    obj.write_text(QUAD_OBJ)
    texture = tmp_path / "tex.png"
    image = Image.new("RGBA", (8, 8), (10, 20, 30, 255))
    for x, alpha in enumerate(alphas):
        image.putpixel((x, 0), (10, 20, 30, alpha))
    image.save(texture)

    objmc.objmc(str(obj), str(texture), [str(tmp_path / "out.json"), str(tmp_path / "out.png")])

    assert Image.open(tmp_path / "out.png").convert("RGBA").getpixel((6, 0))[2] == translucent


def test_objmc_zeroes_transparent_texels(tmp_path):
    import objmc

    obj = tmp_path / "quad.obj"
    obj.write_text(QUAD_OBJ)
    texture = tmp_path / "tex.png"
    # A fully transparent texel with a colour of its own, which is never seen.
    image = Image.new("RGBA", (8, 8), (90, 90, 90, 0))
    image.putpixel((3, 3), (200, 50, 10, 255))
    image.save(texture)

    objmc.objmc(str(obj), str(texture), [str(tmp_path / "out.json"), str(tmp_path / "out.png")])

    # 1 face on an 8 wide texture: 2 header rows + 1 uv row before the padding.
    top, _ = objmc.texture_layout(3, 8, objmc.mipmap)
    baked = Image.open(tmp_path / "out.png").convert("RGBA").crop((0, top, 8, top + 8))
    alphas = list(baked.getchannel("A").getdata())
    assert sorted(alphas) == [0] * 63 + [255]  # the shape is untouched
    assert set(baked.getdata()) == {(200, 50, 10, 255), (0, 0, 0, 0)}


def test_convert_model_flipbook_flags_translucent_texels_in_any_frame(tmp_path):
    input_path, output_path, _ = _setup_basic_convert_inputs(tmp_path)
    _sodium_obj(input_path, "props/lamp", QUAD_OBJ)
    texture = input_path / constants.RELATIVE_SODIUM_TEXTURES_PATH / "props/lamp.png"
    # Frame 0, all objmc sees, is cutout; only frame 1 is partly transparent.
    sheet = Image.new("RGBA", (8, 16), (255, 0, 0, 255))
    sheet.putpixel((0, 0), (0, 0, 0, 0))
    sheet.putpixel((0, 8), (255, 0, 0, 128))
    sheet.save(texture)
    _write_json(Path(str(texture) + ".mcmeta"), {"animation": {}})

    objmc_conversion.convert_sodium_model(
        input_path, output_path, "props/lamp", None, REAL_OBJMC, False, False
    )

    out_texture = output_path / constants.RELATIVE_SODIUM_TEXTURES_PATH / "props/lamp.png"
    frame_height = json.loads(Path(str(out_texture) + ".mcmeta").read_text())["animation"]["height"]
    baked = Image.open(out_texture).convert("RGBA")
    assert [baked.getpixel((6, y))[2] for y in (0, frame_height)] == [1, 1]


def test_convert_model_removes_stale_mcmeta(tmp_path):
    input_path, output_path, objmc_path = _setup_basic_convert_inputs(tmp_path)
    stale = output_path / constants.RELATIVE_SODIUM_TEXTURES_PATH / "props/lamp.png.mcmeta"
    _write_json(stale, {"animation": {}})

    with patch.object(subprocess, "run", side_effect=_make_fake_objmc()):
        objmc_conversion.convert_sodium_model(
            input_path, output_path, "props/lamp", None, objmc_path, False, False
        )

    assert not stale.exists()

# =========================================================================
# Models on blocks the client offsets
# =========================================================================


def test_find_centred_models_notes_the_mcme_models_on_offset_blocks(tmp_path, monkeypatch):
    monkeypatch.setattr(objmc_conversion, "centred_models", set())
    blockstates = tmp_path / "in" / constants.RELATIVE_BLOCKSTATE_PATH
    _write_json(blockstates / "fern.json", {"variants": {"": [
        {"model": "mcme:block/fern"}, {"model": "mcme:block/fern_2", "y": 90},
        {"model": "minecraft:block/fern"},
    ]}})
    _write_json(blockstates / "tall_grass.json", {"multipart": [
        {"when": {"half": "lower"}, "apply": {"model": "mcme:block/tall_grass_bottom"}},
    ]})
    _write_json(blockstates / "stone.json", {"variants": {"": {"model": "mcme:block/rock"}}})

    objmc_conversion.find_centred_models(tmp_path / "in")

    assert objmc_conversion.centred_models == {"block/fern", "block/fern_2", "block/tall_grass_bottom"}


@pytest.mark.parametrize("centred", [True, False])
def test_convert_model_centres_the_carriers_of_a_model_on_an_offset_block(tmp_path, monkeypatch, centred):
    monkeypatch.setattr(objmc_conversion, "centred_models", {"props/lamp"} if centred else set())
    input_path, output_path, objmc_path = _setup_basic_convert_inputs(tmp_path)
    fake = _make_fake_objmc()
    calls = []

    def _recording(cmd, **kwargs):
        calls.append(cmd)
        return fake(cmd, **kwargs)

    with patch.object(subprocess, "run", side_effect=_recording):
        objmc_conversion.convert_sodium_model(
            input_path, output_path, "props/lamp", None, objmc_path, False, False
        )

    assert ("--centred" in calls[0]) == centred


def test_centred_models_never_share_a_parent_with_the_rest(tmp_path, monkeypatch):
    input_path, output_path, _ = _setup_basic_convert_inputs(tmp_path, model_path="props/lamp_parent")
    monkeypatch.setattr(objmc_conversion, "centred_models", set())
    plain = objmc_conversion._plan_conversion(input_path, output_path, "props/lamp_parent", None)
    monkeypatch.setattr(objmc_conversion, "centred_models", {"props/lamp_parent"})
    centred = objmc_conversion._plan_conversion(input_path, output_path, "props/lamp_parent", None)

    assert objmc_conversion._parent_identifier(plain) == "props/lamp_parent"
    assert objmc_conversion._parent_identifier(centred) == "props/lamp_parent_centred"


@pytest.mark.parametrize("centred, flag", [(True, (1, 0, 0, 255)), (False, (0, 0, 0, 255))])
def test_objmc_flags_centred_carriers_in_the_header(tmp_path, centred, flag):
    import objmc

    obj = tmp_path / "quad.obj"
    obj.write_text(QUAD_OBJ)
    texture = tmp_path / "tex.png"
    Image.new("RGBA", (16, 16), (200, 50, 10, 255)).save(texture)

    objmc.objmc(str(obj), str(texture), [str(tmp_path / "out.json"), str(tmp_path / "out.png")], centred=centred)

    assert Image.open(tmp_path / "out.png").convert("RGBA").getpixel((9, 0)) == flag


def test_objmc_keeps_header_and_pointers_nearly_opaque(tmp_path):
    # OptiFine makes nearly transparent pixels fully transparent, and the client
    # then recolours them - so nothing the shader reads may be.
    import objmc

    obj = tmp_path / "quad.obj"
    obj.write_text(QUAD_OBJ)
    texture = tmp_path / "tex.png"
    Image.new("RGBA", (16, 16), (200, 50, 10, 255)).save(texture)

    objmc.objmc(str(obj), str(texture), [str(tmp_path / "out.json"), str(tmp_path / "out.png")])

    bake = Image.open(tmp_path / "out.png").convert("RGBA")
    header = [bake.getpixel((x, 0)) for x in range(16)]
    pointer = bake.getpixel((0, 2))  # the one face's
    assert all(p[3] == 255 for p in header)
    assert pointer[3] == objmc.POINTER_ALPHA
    # the pointer holds its own column and row
    assert (pointer[0] * 16 + (pointer[1] >> 4), (pointer[1] & 15) * 256 + pointer[2]) == (0, 2)
