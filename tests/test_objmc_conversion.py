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
