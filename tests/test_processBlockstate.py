import json
from pathlib import Path
from unittest.mock import patch

import constants
import processBlockstate
import pytest

# ---------- helpers ----------


def _write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def _blockstate(root: Path, data, override: bool = False):
    """Write stone.json into a pack, optionally into its vanilla overrides folder."""
    base = root / constants.RELATIVE_VANILLA_OVERRIDES_PATH if override else root
    _write_json(base / constants.RELATIVE_BLOCKSTATE_PATH / "stone.json", data)


def _models(count):
    return [{"model": f"mcme:props/lamp_{i}"} for i in range(count)]


def _run_models(models, max_model_entries=None):
    """Run a model entry through process_model_entry. Returns the model entries handed
    to processModel.process, in call order; the entry itself is trimmed in place."""
    with patch.object(processBlockstate.processModel, "process") as mock_process:
        processBlockstate.process_model_entry(
            Path("in"),
            Path("out"),
            Path("vanilla"),
            models,
            max_model_entries,
            Path("objmc.py"),
            False,
            False,
        )
    return [call.args[3] for call in mock_process.call_args_list]


# =========================================================================
# process_model_entry()
# =========================================================================


def test_single_model_is_processed():
    model = {"model": "mcme:props/lamp"}
    assert _run_models(model) == [model]


def test_list_is_processed_in_order():
    models = _models(3)
    assert _run_models(models) == models
    assert len(models) == 3  # nothing dropped when unlimited


def test_list_is_trimmed_to_max_model_entries_in_place():
    models = _models(5)
    # Only the retained models are converted, and the entry is trimmed in place
    # so the blockstate written out only references converted models.
    assert _run_models(models, max_model_entries=2) == _models(2)
    assert len(models) == 2


def test_no_limit_keeps_every_model():
    models = _models(2)
    assert _run_models(models, max_model_entries=None) == models
    assert len(models) == 2


def test_max_model_entries_above_length_keeps_everything():
    models = _models(1)
    assert _run_models(models, max_model_entries=10) == models
    assert len(models) == 1


def test_duplicate_models_trim_from_the_end():
    """Identical entries are common in weighted variants — the trim must drop
    the tail, not the first equal element."""
    a, b = {"model": "mcme:props/lamp"}, {"model": "mcme:props/other"}
    models = [a, b, dict(a)]
    _run_models(models, max_model_entries=2)
    assert models == [a, b]


# =========================================================================
# model_entries()
# =========================================================================


def test_model_entries_of_variants_are_the_values():
    variants = {
        "facing=north": {"model": "mcme:props/lamp"},
        "facing=south": [{"model": "mcme:props/lamp"}, {"model": "mcme:props/lamp_2"}],
    }
    assert list(processBlockstate.model_entries({"variants": variants})) == list(
        variants.values()
    )


def test_model_entries_of_multipart_are_the_applies():
    parts = [
        {"apply": {"model": "mcme:props/fence_post"}},
        {"when": {"north": "true"}, "apply": [{"model": "mcme:props/fence_side"}]},
    ]
    assert list(processBlockstate.model_entries({"multipart": parts})) == [
        part["apply"] for part in parts
    ]


def test_model_entries_of_unknown_structure_is_empty():
    assert list(processBlockstate.model_entries({"something_else": {}})) == []


# =========================================================================
# process() — file resolution and dispatch
# =========================================================================


def _run_process(tmp_path, max_model_entries=None):
    processBlockstate.process(
        tmp_path / "in",
        tmp_path / "out",
        tmp_path / "vanilla",
        "stone.json",
        max_model_entries,
        False,
        tmp_path / "objmc.py",
        False,
    )
    return tmp_path / "out" / constants.RELATIVE_BLOCKSTATE_PATH / "stone.json"


@pytest.mark.parametrize(
    "data,expected",
    [
        ({"variants": {"": {"model": "a"}}}, [{"model": "a"}]),
        ({"multipart": [{"apply": {"model": "b"}}]}, [{"model": "b"}]),
        ({"variants": {}}, []),
    ],
    ids=["variants", "multipart", "empty"],
)
def test_process_hands_every_entry_to_process_model_entry(tmp_path, data, expected):
    _blockstate(tmp_path / "in", data)

    with patch.object(
        processBlockstate, "process_model_entry"
    ) as mock_process_model_entry:
        _run_process(tmp_path)

    assert [c.args[3] for c in mock_process_model_entry.call_args_list] == expected


@pytest.mark.parametrize(
    "packs,expected",
    [
        (["override", "rp", "vanilla"], "override"),
        (["rp", "vanilla"], "rp"),
        (["vanilla"], "vanilla"),
    ],
    ids=["override wins", "rp beats vanilla", "vanilla fallback"],
)
def test_process_blockstate_source_precedence(tmp_path, packs, expected):
    for pack in packs:
        root = tmp_path / ("vanilla" if pack == "vanilla" else "in")
        _blockstate(
            root, {"variants": {"": {"model": pack}}}, override=pack == "override"
        )

    with patch.object(
        processBlockstate, "process_model_entry"
    ) as mock_process_model_entry:
        _run_process(tmp_path)

    assert mock_process_model_entry.call_args.args[3] == {"model": expected}


def test_process_writes_blockstate_from_resource_pack(tmp_path):
    _blockstate(tmp_path / "in", {"variants": {"": {"model": "rp"}}})

    with patch.object(processBlockstate, "process_model_entry"):
        output_file = _run_process(tmp_path)

    assert json.loads(output_file.read_text()) == {"variants": {"": {"model": "rp"}}}


def test_process_does_not_write_blockstate_sourced_from_vanilla(tmp_path):
    _blockstate(tmp_path / "vanilla", {"variants": {"": {"model": "vanilla"}}})

    with patch.object(processBlockstate, "process_model_entry"):
        output_file = _run_process(tmp_path)

    assert not output_file.exists()


def test_process_writes_trimmed_blockstate(tmp_path):
    """End-to-end with the real helpers: the blockstate written out only keeps
    the models that were actually converted."""
    _blockstate(tmp_path / "in", {"variants": {"": _models(4)}})

    with patch.object(processBlockstate.processModel, "process"):
        output_file = _run_process(tmp_path, max_model_entries=2)

    assert json.loads(output_file.read_text())["variants"][""] == _models(2)
