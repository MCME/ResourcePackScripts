import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "generateVanilla"))

import pytest

import processModel


@pytest.fixture(autouse=True)
def _reset_converted_models():
    processModel.converted_models.clear()
    yield
    processModel.converted_models.clear()
