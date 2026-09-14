import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import constants
import processModel
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


def _vanilla_texture(input_path: Path, texture_path: str, content: bytes = b"\x89PNG"):
    p = (
        input_path
        / constants.RELATIVE_VANILLA_TEXTURES_PATH
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
        # cmd is the runList: ['python3', objmc, '--objs', ..., '--out', MODEL, TEX, '--visibility', ...]
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
# process() dispatcher
# =========================================================================


def test_process_mcme_no_rotation_passes_no_rotation(tmp_path):
    model_data = {"model": "mcme:some/model"}
    with patch.object(processModel, "convert_model") as mock_convert:
        processModel.process(
            tmp_path / "in",
            tmp_path / "out",
            tmp_path / "vanilla",
            model_data,
            tmp_path / "objmc.py",
            False,
            False,
        )

    mock_convert.assert_called_once()
    args = mock_convert.call_args.args
    assert args[2] == "some/model"
    assert args[3] is None
    assert model_data["model"] == "mcme:some/model"


@pytest.mark.parametrize("axis,angle", [("x", 90), ("y", 180), ("z", 270)])
def test_process_mcme_rotation_updates_model_name(tmp_path, axis, angle):
    model_data = {"model": "mcme:some/model", axis: angle}
    with patch.object(processModel, "convert_model") as mock_convert:
        processModel.process(
            tmp_path / "in",
            tmp_path / "out",
            tmp_path / "vanilla",
            model_data,
            tmp_path / "objmc.py",
            False,
            False,
        )
    assert mock_convert.call_args.args[3] == (axis, angle)
    assert model_data["model"] == f"mcme:some/model_{axis}_{angle}"


def test_process_mcme_multiple_rotations_warns_and_bakes_the_first(tmp_path, capsys):
    """Only one axis can be baked in, so the rest are dropped - loudly, since
    they have already been popped off the entry."""
    model_data = {"model": "mcme:some/model", "x": 90, "y": 180}
    with patch.object(processModel, "convert_model") as mock_convert:
        processModel.process(
            tmp_path / "in",
            tmp_path / "out",
            tmp_path / "vanilla",
            model_data,
            tmp_path / "objmc.py",
            False,
            False,
        )

    warning = capsys.readouterr().out
    assert "WARNING" in warning
    assert "y=180" in warning
    # x wins because it is checked first, and y is gone from the entry entirely
    assert mock_convert.call_args.args[3] == ("x", 90)
    assert model_data == {"model": "mcme:some/model_x_90"}


def test_process_non_mcme_overridden_in_input(tmp_path):
    """The input pack overrides the vanilla model, so the model itself, its
    textures and its parent chain are all copied out of the input pack."""
    input_path = tmp_path / "in"
    output_path = tmp_path / "out"
    vanilla_path = tmp_path / "vanilla"

    model_rel = constants.RELATIVE_VANILLA_MODELS_PATH / Path("block/stone.json")
    _write_json(
        input_path / model_rel,
        {
            "parent": "minecraft:block/cube_all",
            "textures": {"all": "block/stone"},
        },
    )
    # Parent model
    _write_json(
        input_path
        / constants.RELATIVE_VANILLA_MODELS_PATH
        / Path("block/cube_all.json"),
        {"textures": {"particle": "#all"}},
    )
    _vanilla_texture(input_path, "block/stone")

    processModel.process(
        input_path,
        output_path,
        vanilla_path,
        {"model": "minecraft:block/stone"},
        tmp_path / "objmc.py",
        False,
        False,
    )

    assert (output_path / model_rel).exists()
    assert (
        output_path / constants.RELATIVE_VANILLA_MODELS_PATH / "block/cube_all.json"
    ).exists()
    assert (
        output_path / constants.RELATIVE_VANILLA_TEXTURES_PATH / "block/stone.png"
    ).exists()


def test_process_non_mcme_only_in_vanilla(tmp_path):
    """The input pack does not override the model, so the vanilla model is only
    read to learn which textures the input pack overrides."""
    input_path = tmp_path / "in"
    output_path = tmp_path / "out"
    vanilla_path = tmp_path / "vanilla"

    # Model exists only in the vanilla resource pack, not in the input pack
    _write_json(
        vanilla_path / constants.RELATIVE_VANILLA_MODELS_PATH / Path("block/dirt.json"),
        {"textures": {"all": "block/dirt"}},
    )
    # ...but the input pack overrides its texture
    _vanilla_texture(input_path, "block/dirt")

    processModel.process(
        input_path,
        output_path,
        vanilla_path,
        {"model": "minecraft:block/dirt"},
        tmp_path / "objmc.py",
        False,
        False,
    )

    # Model itself should NOT be copied — only the textures from the RP
    assert not (
        output_path / constants.RELATIVE_VANILLA_MODELS_PATH / "block/dirt.json"
    ).exists()
    assert (
        output_path / constants.RELATIVE_VANILLA_TEXTURES_PATH / "block/dirt.png"
    ).exists()


def test_process_vanilla_missing_everywhere_warns(tmp_path, capsys):
    processModel.process(
        tmp_path / "in",
        tmp_path / "out",
        tmp_path / "vanilla",
        {"model": "minecraft:block/does_not_exist"},
        tmp_path / "objmc.py",
        False,
        False,
    )
    out = capsys.readouterr().out
    assert "WARNING" in out
    assert "does_not_exist" in out


# =========================================================================
# copy_textures()
# =========================================================================


def test_copy_textures_defaults_to_vanilla_namespace(tmp_path):
    input_path = tmp_path / "in"
    output_path = tmp_path / "out"

    _vanilla_texture(input_path, "block/x")

    processModel.copy_textures(
        input_path, output_path, {"textures": {"all": "block/x"}}, False
    )

    assert (
        output_path / constants.RELATIVE_VANILLA_TEXTURES_PATH / "block/x.png"
    ).exists()


def test_copy_textures_mcme_namespace_uses_sodium_path(tmp_path):
    input_path = tmp_path / "in"
    output_path = tmp_path / "out"

    _sodium_texture(input_path, "custom/tex")

    processModel.copy_textures(
        input_path, output_path, {"textures": {"all": "mcme:custom/tex"}}, False
    )

    assert (
        output_path / constants.RELATIVE_SODIUM_TEXTURES_PATH / "custom/tex.png"
    ).exists()


def test_copy_textures_copies_mcmeta_when_present(tmp_path):
    input_path = tmp_path / "in"
    output_path = tmp_path / "out"

    _vanilla_texture(input_path, "block/animated")
    mcmeta_rel = constants.RELATIVE_VANILLA_TEXTURES_PATH / Path(
        "block/animated" + constants.TEXTURE_EXTENSION + constants.MCMETA_EXTENSION
    )
    _write_text(input_path / mcmeta_rel, '{"animation":{}}')

    processModel.copy_textures(
        input_path, output_path, {"textures": {"all": "block/animated"}}, False
    )

    assert (output_path / mcmeta_rel).exists()


def test_copy_textures_resolves_any_namespace(tmp_path):
    """Every namespace resolves to its own assets folder - there is no whitelist
    of known namespaces, so a pack can name textures in any of them."""
    input_path = tmp_path / "in"
    output_path = tmp_path / "out"

    texture_rel = Path("assets/modelengine/textures/entity/aragorn.png")
    (input_path / texture_rel).parent.mkdir(parents=True, exist_ok=True)
    (input_path / texture_rel).write_bytes(b"\x89PNG")

    processModel.copy_textures(
        input_path,
        output_path,
        {"textures": {"all": "modelengine:entity/aragorn"}},
        False,
    )

    assert (output_path / texture_rel).exists()


def test_copy_textures_skips_variable_references(tmp_path):
    """A #name value points at another texture slot, not a file."""
    input_path = tmp_path / "in"
    output_path = tmp_path / "out"

    processModel.copy_textures(
        input_path, output_path, {"textures": {"all": "#side"}}, False
    )

    assert not output_path.exists() or not any(output_path.rglob("*.png"))


# =========================================================================
# copy_model_chain()
# =========================================================================


def _minecraft_model(pack: Path, model_path: str, data):
    _write_json(pack / _model_rel(model_path), data)


def _model_rel(model_path: str) -> Path:
    return constants.RELATIVE_VANILLA_MODELS_PATH / Path(
        model_path + constants.VANILLA_MODEL_EXTENSION
    )


def test_copy_model_chain_walks_past_models_the_pack_does_not_override(tmp_path):
    """A four deep chain where the resource pack overrides only the 2nd and 4th
    models. The walk has to carry on through the links it does not override to
    reach them: the 2nd is an overridden parent whose only child is a stock
    vanilla model, the 4th an overridden grandparent behind a parent that is
    not overridden."""
    input_path = tmp_path / "in"
    output_path = tmp_path / "out"
    vanilla_path = tmp_path / "vanilla"

    _minecraft_model(vanilla_path, "block/stone", {"parent": "block/cube_all"})
    _minecraft_model(vanilla_path, "block/cube_all", {"parent": "block/block"})
    _minecraft_model(vanilla_path, "block/block", {"parent": "block/root"})
    _minecraft_model(vanilla_path, "block/root", {"elements": []})
    # the pack's own version of two links in that chain
    _minecraft_model(input_path, "block/cube_all", {"parent": "block/block"})
    _minecraft_model(input_path, "block/root", {"elements": []})

    processModel.copy_model_chain(
        input_path, output_path, vanilla_path, "block/stone", False
    )

    assert (output_path / _model_rel("block/cube_all")).exists()
    assert (output_path / _model_rel("block/root")).exists()
    # models the pack does not override are left to the client's own copy
    assert not (output_path / _model_rel("block/stone")).exists()
    assert not (output_path / _model_rel("block/block")).exists()


def test_copy_model_chain_copies_a_texture_named_only_by_a_parent(tmp_path):
    """The pack retextures a block but overrides no model at all. The texture is
    named by the parent, so it is only found by reading the whole chain."""
    input_path = tmp_path / "in"
    output_path = tmp_path / "out"
    vanilla_path = tmp_path / "vanilla"

    _minecraft_model(vanilla_path, "block/stone", {"parent": "block/cube_all"})
    _minecraft_model(
        vanilla_path, "block/cube_all", {"textures": {"particle": "block/parent_tex"}}
    )
    _vanilla_texture(input_path, "block/parent_tex")

    processModel.copy_model_chain(
        input_path, output_path, vanilla_path, "block/stone", False
    )

    assert (
        output_path / constants.RELATIVE_VANILLA_TEXTURES_PATH / "block/parent_tex.png"
    ).exists()
    # no model was overridden, so no model file should be written
    assert not any(output_path.rglob("*.json"))


def test_copy_model_chain_mcme_parent_uses_sodium_path(tmp_path):
    input_path = tmp_path / "in"
    output_path = tmp_path / "out"
    vanilla_path = tmp_path / "vanilla"

    parent_rel = constants.RELATIVE_SODIUM_MODELS_PATH / Path("custom/parent.json")
    _minecraft_model(input_path, "block/child", {"parent": "mcme:custom/parent"})
    _write_json(input_path / parent_rel, {"elements": []})

    processModel.copy_model_chain(
        input_path, output_path, vanilla_path, "block/child", False
    )

    assert (output_path / parent_rel).exists()


def test_copy_model_chain_warns_when_a_parent_is_missing_everywhere(tmp_path, capsys):
    input_path = tmp_path / "in"
    output_path = tmp_path / "out"
    vanilla_path = tmp_path / "vanilla"

    _minecraft_model(vanilla_path, "block/stone", {"parent": "block/absent_parent"})

    processModel.copy_model_chain(
        input_path, output_path, vanilla_path, "block/stone", False
    )

    out = capsys.readouterr().out
    assert "WARNING" in out
    assert "absent_parent" in out


def test_copy_model_chain_survives_a_parent_cycle(tmp_path):
    """A hand authored pack can point two models at each other. The walk must
    stop rather than recurse until Python gives up."""
    input_path = tmp_path / "in"
    output_path = tmp_path / "out"
    vanilla_path = tmp_path / "vanilla"

    _minecraft_model(input_path, "block/a", {"parent": "block/b"})
    _minecraft_model(input_path, "block/b", {"parent": "block/a"})

    processModel.copy_model_chain(
        input_path, output_path, vanilla_path, "block/a", False
    )

    assert (output_path / _model_rel("block/a")).exists()
    assert (output_path / _model_rel("block/b")).exists()


def test_copy_model_chain_stops_at_a_builtin_parent(tmp_path, capsys):
    """builtin/ names a model the client draws itself, so there is no file to
    look for and nothing to warn about."""
    input_path = tmp_path / "in"
    output_path = tmp_path / "out"
    vanilla_path = tmp_path / "vanilla"

    _minecraft_model(input_path, "item/sword", {"parent": "builtin/generated"})

    processModel.copy_model_chain(
        input_path, output_path, vanilla_path, "item/sword", False
    )

    assert (output_path / _model_rel("item/sword")).exists()
    assert "WARNING" not in capsys.readouterr().out


def test_copy_model_chain_stops_at_a_model_with_no_parent(tmp_path):
    input_path = tmp_path / "in"
    output_path = tmp_path / "out"
    vanilla_path = tmp_path / "vanilla"

    _minecraft_model(input_path, "block/leaf", {"elements": []})

    processModel.copy_model_chain(
        input_path, output_path, vanilla_path, "block/leaf", False
    )

    assert [p.name for p in output_path.rglob("*.json")] == ["leaf.json"]


# =========================================================================
# convert_model() — subset
# =========================================================================


def _setup_basic_convert_inputs(
    tmp_path,
    model_path="props/lamp",
    model_content=None,
    extra_mtl_texture="mcme:props/lamp",
):
    """Lay out the minimum files convert_model needs: model json stub, obj file, mtl file."""
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
        processModel.convert_model(
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
        processModel.convert_model(
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
    # convert_model rewrites texture refs to mcme:<output_texture_path>
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
    assert processModel.converted_models["props/lamp"] == out_model


def test_convert_model_rotation_creates_and_cleans_rotated_obj(tmp_path):
    input_path, output_path, objmc_path = _setup_basic_convert_inputs(tmp_path)

    with (
        patch.object(subprocess, "run", side_effect=_make_fake_objmc()),
        patch.object(processModel.rotate_obj, "rotate_obj_file") as mock_rotate,
    ):
        # rotate_obj_file must actually create the rotated file so the pipeline can
        # continue and the cleanup step at the end can unlink it.
        def _fake_rotate(src, dst, axis, angle):
            Path(dst).write_text("# rotated obj")

        mock_rotate.side_effect = _fake_rotate

        processModel.convert_model(
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
    assert angle == -90  # convert_model negates the angle
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
        processModel.convert_model(
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
        with patch.object(processModel.rotate_obj, "rotate_obj_file") as mock_rotate:

            def _fake_rotate(src, dst, axis, angle):
                Path(dst).write_text("# rotated obj")

            mock_rotate.side_effect = _fake_rotate
            processModel.convert_model(
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
    assert processModel.converted_models["props/lamp"] == constants.PARENT_DONE_VALUE
