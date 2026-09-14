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
    at whatever path is passed via `--out`. Returns a completed-process mock."""

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
        tex_out.write_bytes(b"\x89PNG_fake")
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
    # First conversion — should be registered in converted_models
    assert objmc_conversion.converted_models["props/lamp"] == out_model


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
    """When the same model_path is converted twice, the second call turns both
    resulting model files into children of a shared *_parent file."""
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
        # Second call for the same model_path with a rotation — this triggers the
        # shared-parent extraction branch (line 222 in processModel.py).
        with patch.object(objmc_conversion.rotate_obj, "rotate_obj_file") as mock_rotate:

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

    first_model = (
        output_path / constants.RELATIVE_SODIUM_MODELS_PATH / "props/lamp.json"
    )
    rotated_model = (
        output_path / constants.RELATIVE_SODIUM_MODELS_PATH / "props/lamp_y_90.json"
    )
    parent_model = (
        output_path
        / constants.RELATIVE_SODIUM_MODELS_PATH
        / ("props/lamp" + constants.PARENT_SUFFIX + constants.VANILLA_MODEL_EXTENSION)
    )

    assert first_model.exists()
    assert rotated_model.exists()
    assert parent_model.exists()

    # The originally-converted model should now be a child pointing at the parent
    first_data = json.loads(first_model.read_text())
    assert (
        first_data["parent"]
        == f"{constants.MCME_NAMESPACE}:props/lamp{constants.PARENT_SUFFIX}"
    )
    assert "elements" not in first_data

    # The parent should carry the shape but no textures
    parent_data = json.loads(parent_model.read_text())
    assert "textures" not in parent_data
    assert "elements" in parent_data

    # And converted_models should be marked done
    assert objmc_conversion.converted_models["props/lamp"] == constants.PARENT_DONE_VALUE
