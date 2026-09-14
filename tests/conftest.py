import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "generateVanilla"))

import pytest

import processModel


def pytest_addoption(parser):
    parser.addoption(
        "--objmc",
        action="append",
        default=[],
        metavar="PATH",
        help=(
            "Path to an objmc.py to run the golden tests against. Repeatable - "
            "pass it twice to run the same goldens through two versions and diff "
            "them. Falls back to $OBJMC_PATH, then ./objmc.py."
        ),
    )
    parser.addoption(
        "--update-goldens",
        action="store_true",
        default=False,
        help="Rewrite the golden files from this run's output instead of comparing.",
    )


def objmc_paths(config) -> list[Path]:
    """Every objmc the golden tests should run against, in the order given.

    Mirrors the --objmc default in generateVanilla.py so a bare pytest run picks
    up the same script the pipeline would.
    """
    given = config.getoption("--objmc") or [
        p for p in os.environ.get("OBJMC_PATH", "").split(os.pathsep) if p
    ] or ["objmc.py"]
    return [Path(p).expanduser().resolve() for p in given]


@pytest.fixture(autouse=True)
def _reset_converted_models():
    processModel.converted_models.clear()
    yield
    processModel.converted_models.clear()
