import json
from pathlib import Path
from unittest.mock import patch

import constants
import objmc_conversion
import processModel
import pytest

# ---------- filesystem helpers ----------


def _write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def _write_text(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)








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




# =========================================================================
# process() dispatcher
# =========================================================================


def test_process_mcme_no_rotation_passes_no_rotation(tmp_path):
    model_data = {"model": "mcme:some/model"}
    with patch.object(objmc_conversion, "convert_sodium_model") as mock_convert:
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
    with patch.object(objmc_conversion, "convert_sodium_model") as mock_convert:
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
    with patch.object(objmc_conversion, "convert_sodium_model") as mock_convert:
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


def test_copy_textures_reads_the_sprite_of_an_object_value(tmp_path):
    """Since 1.21.6 a texture value can be an object carrying the identifier
    under `sprite` alongside rendering flags - the stained glass panes do this."""
    input_path = tmp_path / "in"
    output_path = tmp_path / "out"
    _vanilla_texture(input_path, "block/black_stained_glass")

    processModel.copy_textures(
        input_path,
        output_path,
        {
            "textures": {
                "pane": {
                    "force_translucent": True,
                    "sprite": "minecraft:block/black_stained_glass",
                }
            }
        },
        False,
    )

    assert (
        output_path
        / constants.RELATIVE_VANILLA_TEXTURES_PATH
        / "block/black_stained_glass.png"
    ).exists()


def test_copy_textures_skips_a_sprite_object_naming_a_variable(tmp_path):
    """The `sprite` key carries an identifier, so it can be a #reference too."""
    input_path = tmp_path / "in"
    output_path = tmp_path / "out"

    processModel.copy_textures(
        input_path, output_path, {"textures": {"pane": {"sprite": "#side"}}}, False
    )

    assert not output_path.exists() or not any(output_path.rglob("*.png"))


def test_copy_textures_warns_on_an_unrecognised_value_and_continues(tmp_path, capsys):
    """An unknown shape must not stop the rest of the model being copied, but it
    must be visible - a silent skip would hide a format change."""
    input_path = tmp_path / "in"
    output_path = tmp_path / "out"
    _vanilla_texture(input_path, "block/stone")

    processModel.copy_textures(
        input_path,
        output_path,
        {"textures": {"odd": ["0"], "all": "block/stone"}},
        False,
    )

    warning = capsys.readouterr().out
    assert "WARNING" in warning
    assert "odd" in warning
    # the well-formed entry alongside it is still copied
    assert (
        output_path / constants.RELATIVE_VANILLA_TEXTURES_PATH / "block/stone.png"
    ).exists()


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
