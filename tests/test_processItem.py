import json
from pathlib import Path
from unittest.mock import patch

import constants
import processItem
import pytest

# ---------- helpers ----------


def _write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def _item(root: Path, data, override: bool = False):
    """Write diamond_sword.json into a pack, optionally into its vanilla overrides."""
    base = root / constants.RELATIVE_VANILLA_OVERRIDES_PATH if override else root
    _write_json(base / constants.RELATIVE_ITEMS_PATH / "diamond_sword.json", data)


def _model(identifier, model_type="minecraft:model"):
    return {"type": model_type, "model": identifier}


def _found(definition):
    """The identifiers model_identifier_fields picks out, in order."""
    return [
        node[field] for node, field in processItem.model_identifier_fields(definition)
    ]


def _run_process(tmp_path):
    processItem.process(
        tmp_path / "in",
        tmp_path / "out",
        tmp_path / "vanilla",
        "diamond_sword.json",
        False,
        tmp_path / "objmc.py",
        False,
    )
    return tmp_path / "out" / constants.RELATIVE_ITEMS_PATH / "diamond_sword.json"


# =========================================================================
# model_identifier_fields() — leaves
# =========================================================================


def test_a_model_names_its_model_field():
    assert _found({"model": _model("item/sword")}) == ["item/sword"]


@pytest.mark.parametrize("model_type", ["minecraft:model", "model"])
def test_the_namespace_prefix_is_optional(model_type):
    """Both spellings appear in real packs."""
    assert _found({"model": _model("item/sword", model_type)}) == ["item/sword"]


def test_a_special_names_its_base_not_its_model():
    """special's "model" is the client's renderer, not a file — only "base" is one."""
    definition = {
        "model": {
            "type": "minecraft:special",
            "base": "item/template_skull",
            "model": {"type": "minecraft:head", "kind": "player"},
        }
    }
    assert _found(definition) == ["item/template_skull"]


def test_a_type_that_names_no_model_is_ignored():
    assert _found({"model": {"type": "minecraft:empty"}}) == []


def test_a_node_with_no_type_is_ignored():
    """The definition's own top level has a "model" key holding a node, not a file."""
    assert _found({"model": {"models": []}}) == []


def test_a_non_string_model_field_is_ignored():
    assert _found({"model": {"type": "minecraft:model", "model": {"nested": 1}}}) == []


def test_tints_are_not_models():
    definition = {
        "model": {
            "type": "minecraft:model",
            "model": "item/sword",
            "tints": [
                {"type": "minecraft:custom_model_data", "index": 0, "default": 0}
            ],
        }
    }
    assert _found(definition) == ["item/sword"]


# =========================================================================
# model_identifier_fields() — containers
# =========================================================================


def test_composite_names_every_model_it_holds():
    definition = {
        "model": {
            "type": "minecraft:composite",
            "models": [_model("a"), _model("b"), _model("c")],
        }
    }
    assert _found(definition) == ["a", "b", "c"]


def test_range_dispatch_names_its_entries_and_fallback():
    definition = {
        "model": {
            "type": "minecraft:range_dispatch",
            "property": "custom_model_data",
            "fallback": _model("fallback"),
            "entries": [
                {"threshold": 1, "model": _model("one")},
                {"threshold": 2, "model": _model("two")},
            ],
        }
    }
    assert sorted(_found(definition)) == ["fallback", "one", "two"]


def test_select_names_its_cases_and_fallback():
    definition = {
        "model": {
            "type": "minecraft:select",
            "property": "minecraft:display_context",
            "cases": [{"when": "gui", "model": _model("in_gui")}],
            "fallback": _model("fallback"),
        }
    }
    assert sorted(_found(definition)) == ["fallback", "in_gui"]


def test_condition_names_both_branches():
    definition = {
        "model": {
            "type": "minecraft:condition",
            "property": "minecraft:broken",
            "on_true": _model("broken"),
            "on_false": _model("intact"),
        }
    }
    assert sorted(_found(definition)) == ["broken", "intact"]


def test_containers_nest():
    """A select inside a select is ordinary recursion, not a special case."""
    definition = {
        "model": {
            "type": "minecraft:select",
            "cases": [
                {
                    "when": "gui",
                    "model": {
                        "type": "minecraft:select",
                        "cases": [{"when": "x", "model": _model("deep")}],
                    },
                }
            ],
        }
    }
    assert _found(definition) == ["deep"]


def test_a_deeply_nested_definition_names_every_model():
    """Every container type nested inside every other, with models at four
    different depths — the shape a real dispatch item grows into."""
    definition = {
        "model": {
            "type": "minecraft:range_dispatch",
            "property": "custom_model_data",
            "fallback": _model("dispatch_fallback"),
            "entries": [
                {
                    "threshold": 1,
                    "model": {
                        "type": "minecraft:select",
                        "property": "minecraft:display_context",
                        "cases": [
                            {
                                "when": "gui",
                                "model": {
                                    "type": "minecraft:composite",
                                    "models": [
                                        _model("gui_base"),
                                        {
                                            "type": "minecraft:condition",
                                            "property": "minecraft:broken",
                                            "on_true": _model("gui_broken"),
                                            "on_false": {
                                                "type": "minecraft:special",
                                                "base": "gui_skull",
                                                "model": {
                                                    "type": "minecraft:head",
                                                    "kind": "player",
                                                },
                                            },
                                        },
                                    ],
                                },
                            }
                        ],
                        "fallback": _model("held"),
                    },
                },
                {"threshold": 2, "model": _model("cmd_2")},
            ],
        }
    }

    found = _found(definition)

    assert sorted(found) == [
        "cmd_2",
        "dispatch_fallback",
        "gui_base",
        "gui_broken",
        "gui_skull",
        "held",
    ]
    # nothing counted twice on the way back up
    assert len(found) == 6


def test_an_unknown_container_cannot_hide_its_models():
    """The reason the walk is not driven by a table of container types: a type
    added to the format in a later version must not silently drop its subtree."""
    definition = {
        "model": {
            "type": "minecraft:something_invented_later",
            "whatever": [_model("still_found")],
        }
    }
    assert _found(definition) == ["still_found"]


# =========================================================================
# model_identifier_fields() — write-back
# =========================================================================


def test_the_field_can_be_written_back_through():
    """processModel points a model entry at the converted model, and the item
    model definition has to pick that up."""
    definition = {"model": _model("mcme:block/leaves")}

    for node, field in processItem.model_identifier_fields(definition):
        node[field] = "mcme:block/leaves_converted"

    assert definition["model"]["model"] == "mcme:block/leaves_converted"


# =========================================================================
# process()
# =========================================================================


@pytest.mark.parametrize(
    "packs,expected",
    [
        (["override", "rp", "vanilla"], "override"),
        (["rp", "vanilla"], "rp"),
        (["vanilla"], "vanilla"),
    ],
    ids=["override wins", "rp beats vanilla", "vanilla fallback"],
)
def test_process_item_definition_source_precedence(tmp_path, packs, expected):
    for pack in packs:
        root = tmp_path / ("vanilla" if pack == "vanilla" else "in")
        _item(root, {"model": _model(pack)}, override=pack == "override")

    with patch.object(processItem.processModel, "process") as mock_process:
        _run_process(tmp_path)

    assert mock_process.call_args.args[3] == {"model": expected}


def test_process_hands_every_model_to_process_model(tmp_path):
    _item(
        tmp_path / "in",
        {"model": {"type": "composite", "models": [_model("a"), _model("b")]}},
    )

    with patch.object(processItem.processModel, "process") as mock_process:
        _run_process(tmp_path)

    assert [c.args[3] for c in mock_process.call_args_list] == [
        {"model": "a"},
        {"model": "b"},
    ]


def test_process_writes_item_definition_from_resource_pack(tmp_path):
    _item(tmp_path / "in", {"model": _model("item/sword")})

    with patch.object(processItem.processModel, "process"):
        output_file = _run_process(tmp_path)

    assert json.loads(output_file.read_text()) == {"model": _model("item/sword")}


def test_process_does_not_write_item_definition_sourced_from_vanilla(tmp_path):
    _item(tmp_path / "vanilla", {"model": _model("item/sword")})

    with patch.object(processItem.processModel, "process"):
        output_file = _run_process(tmp_path)

    assert not output_file.exists()


def test_process_writes_back_a_converted_identifier(tmp_path):
    """A sodium model is converted under a new name, and the definition written
    out has to name the converted model rather than the loader stub."""
    _item(tmp_path / "in", {"model": _model("mcme:block/leaves")})

    def _convert(input_path, output_path, vanilla_path, entry, *args):
        entry["model"] = "mcme:block/leaves_x90"

    with patch.object(processItem.processModel, "process", side_effect=_convert):
        output_file = _run_process(tmp_path)

    written = json.loads(output_file.read_text())
    assert written["model"]["model"] == "mcme:block/leaves_x90"
