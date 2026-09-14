"""Golden tests pinning the real output of the objmc script.

Every other test in this suite fakes the objmc subprocess, which is right for
testing our own logic but pins nothing about what objmc actually produces. These
run the real script, so they are skipped unless one is available.

Their job is not simply to pass. When objmc is upgraded the goldens are
*supposed* to move - reading that diff is the whole point of having them.
Regenerate with --update-goldens once a change has been understood and accepted.

    pytest tests/test_objmc_golden.py --objmc ../mcme-objmc/objmc.py
    pytest tests/test_objmc_golden.py --objmc ../mcme-objmc/objmc.py --objmc ../objmc/objmc.py

What gets recorded, and why it differs by file:

* the converted model JSON, in full - this is what our code shapes, so the
  content is the thing under test
* copied parent files, as a hash plus the fixture they came from - these are a
  verbatim shutil.copy of a committed fixture, so full content would duplicate
  ~50KB to no purpose, while the hash still asserts the copy is faithful
* textures, as a hash plus dimensions - objmc bakes the geometry into the PNG
  rather than the model JSON, so this is where a conversion change actually
  shows up. The dimensions are recorded because "64x64 became 128x64" is a
  legible diff where a bare hash change is not.
"""

import functools
import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import constants
import objmc_conversion
import pytest
from conftest import objmc_paths

FIXTURE_PACK = Path(__file__).parent / "fixtures" / "sodium_pack"
GOLDEN_DIR = Path(__file__).parent / "goldens"


@dataclass(frozen=True)
class Case:
    name: str
    # (model_path, rotation) pairs, applied in order against one shared
    # converted_models dict - a sequence, because some branches only appear on
    # the second conversion of the same model.
    conversions: tuple
    covers: str = ""


CASES = [
    Case("pine_leaves_brown", (("block/pine_leaves_brown", None),),
         "ordinary: .objmeta parent, mtl_override, texture from .mtl"),
    Case("maple_leaves_shared_obj", (("block/maple_leaves", None),),
         "a second model sharing leaves_parent.obj"),
    Case("no_objmeta", (("block/spruce_thin_trunk_vertical", None),),
         "no .objmeta at all; no manual parent"),
    Case("omnidirectional_rotated", (("block/forestfloor", ("y", 90)),),
         "omnidirectional_parent: rotation must NOT append the _1_N suffix"),
    Case("rotated_parent_found", (("block/spruce_leaves_omnidirectional", ("y", 90)),),
         "rotated manual parent whose _1_2 variant exists"),
    Case("rotated_parent_missing", (("block/pine_leaves_brown", ("y", 180)),),
         "rotated manual parent with no _1_3 variant: warns, falls back"),
    Case("synthetic_options", (("block/synthetic_options", None),),
         "texture, output_texture, offset, visibility, options"),
    Case("synthetic_vanilla_texture", (("block/synthetic_vanilla_texture", None),),
         "minecraft:-namespace texture -> vanilla textures path"),
    # Must be a model with no `parent` in its .objmeta: a manual parent takes
    # priority in convert_model, so with one set this branch is never reached.
    Case("shared_parent_extraction",
         (("block/spruce_thin_trunk_vertical", None),
          ("block/spruce_thin_trunk_vertical", ("y", 90))),
         "same model twice, no manual parent: both outputs become children of a shared *_parent"),
]


def pytest_generate_tests(metafunc):
    """One test instance per (case, objmc). Skips cleanly when objmc is unusable."""
    if "objmc" not in metafunc.fixturenames:
        return

    skip = _why_objmc_unusable(metafunc.config)
    if skip:
        metafunc.parametrize(
            "objmc", [pytest.param(None, marks=pytest.mark.skip(reason=skip))]
        )
        return

    paths = objmc_paths(metafunc.config)
    metafunc.parametrize("objmc", paths, ids=[_objmc_id(p) for p in paths])


def _objmc_id(path: Path) -> str:
    # The containing directory is what distinguishes checkouts - every one of
    # them is named objmc.py.
    return f"{path.parent.name}/{path.name}"


def _why_objmc_unusable(config) -> str | None:
    paths = objmc_paths(config)
    missing = [p for p in paths if not p.exists()]
    if missing:
        return (
            f"objmc not found at {', '.join(str(p) for p in missing)} - "
            "pass --objmc PATH or set $OBJMC_PATH"
        )
    try:
        import PIL  # noqa: F401
    except ImportError:
        # objmc runs under sys.executable (see processModel.convert_model), so
        # the interpreter running pytest is exactly the one that needs PIL.
        # Without this check a broken environment surfaces as a golden mismatch
        # rather than a missing dependency, which is a miserable thing to debug.
        return "PIL is not importable by this interpreter - pip install -r requirements.txt"
    return None


@functools.lru_cache(maxsize=None)
def _objmc_launch_failure(objmc: Path) -> str | None:
    """Whether objmc can be started at all. Checked once per path.

    convert_model catches CalledProcessError and carries on, so an objmc that
    cannot even be imported produces a conversion that quietly writes nothing -
    which the golden comparison would then report as every output having
    vanished. That reads as "objmc changed enormously" when it actually means
    "objmc never ran". Diagnose it up front so the real cause is named.
    """
    result = subprocess.run(
        [sys.executable, str(objmc), "--help"], capture_output=True, text=True
    )
    if result.returncode == 0:
        return None
    stderr = result.stderr.strip().splitlines()
    tail = "\n".join(stderr[-6:]) if stderr else "(nothing on stderr)"
    return (
        f"{objmc} exits {result.returncode} when run under {sys.executable}.\n"
        f"This is an environment problem, not a golden change.\n{tail}"
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture_index() -> dict[str, str]:
    """sha256 -> fixture-relative path, for recognising files that were copied."""
    return {
        _sha256(f): str(f.relative_to(FIXTURE_PACK))
        for f in FIXTURE_PACK.rglob("*")
        if f.is_file()
    }


def _describe_texture(path: Path) -> dict:
    from PIL import Image

    with Image.open(path) as image:
        width, height, mode = image.width, image.height, image.mode
    return {
        "kind": "texture",
        "width": width,
        "height": height,
        "mode": mode,
        "sha256": _sha256(path),
    }


def _capture(out_dir: Path) -> dict:
    """Describe everything a conversion wrote, keyed by pack-relative path."""
    copied_from = _fixture_index()
    outputs = {}
    for f in sorted(out_dir.rglob("*")):
        if not f.is_file():
            continue
        rel = str(f.relative_to(out_dir))
        if f.suffix == constants.TEXTURE_EXTENSION:
            outputs[rel] = _describe_texture(f)
        elif (source := copied_from.get(_sha256(f))) is not None:
            # Byte-identical to a fixture file: a shutil.copy, not objmc output.
            outputs[rel] = {"kind": "copied", "from": source}
        else:
            outputs[rel] = {
                "kind": "converted_model",
                "content": json.loads(f.read_text()),
            }
    return outputs


def _run_case(case: Case, out_dir: Path, objmc: Path) -> dict:
    for model_path, rotation in case.conversions:
        objmc_conversion.convert_sodium_model(
            FIXTURE_PACK, out_dir, model_path, rotation, objmc, False, False
        )
    return {
        "case": case.name,
        "covers": case.covers,
        "conversions": [
            {"model": m, "rotation": list(r) if r else None}
            for m, r in case.conversions
        ],
        "outputs": _capture(out_dir),
    }


def _normalise(value):
    """Round-trip through JSON so tuples compare equal to the lists in goldens."""
    return json.loads(json.dumps(value))


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.name)
def test_objmc_golden(case, objmc, tmp_path, request):
    if (launch_failure := _objmc_launch_failure(objmc)) is not None:
        pytest.fail(launch_failure, pytrace=False)

    out_dir = tmp_path / "out"
    actual = _normalise(_run_case(case, out_dir, objmc))

    golden_file = GOLDEN_DIR / f"{case.name}.json"

    if request.config.getoption("--update-goldens") or not golden_file.exists():
        golden_file.parent.mkdir(parents=True, exist_ok=True)
        golden_file.write_text(json.dumps(actual, indent=2, sort_keys=True) + "\n")
        pytest.skip(f"wrote golden {golden_file.relative_to(Path.cwd())}")

    expected = json.loads(golden_file.read_text())
    if not actual["outputs"] and expected["outputs"]:
        pytest.fail(
            f"{case.name}: the conversion wrote no files at all using {objmc}, "
            "though the golden expects some. convert_model swallows objmc "
            "failures - check objmc's stderr in the captured output above.",
            pytrace=False,
        )
    if actual != expected:
        pytest.fail(_diff_report(case, objmc, expected, actual), pytrace=False)


def _diff_report(case, objmc, expected, actual) -> str:
    import difflib

    lines = [
        f"golden mismatch for {case.name} using {objmc}",
        f"  covers: {case.covers}",
        "",
        "If this is an intended objmc change, review the diff then rerun with",
        "--update-goldens to adopt it.",
        "",
    ]
    lines += list(
        difflib.unified_diff(
            json.dumps(expected, indent=2, sort_keys=True).splitlines(),
            json.dumps(actual, indent=2, sort_keys=True).splitlines(),
            fromfile="golden",
            tofile="actual",
            lineterm="",
        )
    )
    return "\n".join(lines)
