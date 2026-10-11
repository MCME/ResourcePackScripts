"""Helpers for the release automation's tests. Not a test module itself."""

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def load_rp_release():
    """automation/pipeline/rp-release.py as a module: its name has a dash, so it can't be imported."""
    spec = importlib.util.spec_from_file_location("rp_release", REPO_ROOT / "automation" / "pipeline" / "rp-release.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
