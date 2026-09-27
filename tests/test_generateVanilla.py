"""End-to-end tests of generateVanilla.py's copying, run as the script it is.

The generated pack is published, so nothing a symlink in the input pack points
at outside that pack may end up in it. The runs here point at an empty vanilla
pack, so there are no blockstates or items to convert and only the copying
stages have work to do.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "generateVanilla" / "generateVanilla.py"

SECRET = b"HOST SECRET"


def _symlink_or_skip(link: Path, target: Path):
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.symlink(target, link, target_is_directory=target.is_dir())
    except OSError as e:
        # Windows only allows symlinks in Developer Mode or as administrator
        pytest.skip(f"cannot create symlinks here: {e}")


@pytest.fixture
def host(tmp_path):
    """A folder outside the pack, standing in for the rest of the machine."""
    host = tmp_path / "host"
    host.mkdir()
    (host / "id_ed25519").write_bytes(SECRET)
    return host


@pytest.fixture
def pack(tmp_path):
    pack = tmp_path / "pack"
    (pack / "assets").mkdir(parents=True)
    (pack / "vanilla").mkdir()
    return pack


def _generate(tmp_path, pack):
    output = tmp_path / "out"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(pack), str(output), str(tmp_path / "rp")],
        # util.py writes debug.log into the working directory
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return output, result.stdout


def _published_bytes(output: Path) -> bytes:
    return b"".join(p.read_bytes() for p in output.rglob("*") if p.is_file())


def test_a_symlinked_asset_leading_outside_the_pack_is_not_copied(
    tmp_path, pack, host
):
    _symlink_or_skip(pack / "assets/mcme/textures/font/glyph.png", host / "id_ed25519")

    output, out = _generate(tmp_path, pack)

    assert SECRET not in _published_bytes(output)
    assert "outside the pack" in out


def test_a_symlinked_folder_leading_outside_the_pack_is_not_copied(
    tmp_path, pack, host
):
    _symlink_or_skip(pack / "assets/mcme/textures/font", host)

    output, out = _generate(tmp_path, pack)

    assert SECRET not in _published_bytes(output)
    assert "outside the pack" in out


def test_a_symlinked_assets_folder_leading_outside_the_pack_is_not_copied(
    tmp_path, pack, host
):
    (pack / "assets").rmdir()
    _symlink_or_skip(pack / "assets", host)

    output, out = _generate(tmp_path, pack)

    assert SECRET not in _published_bytes(output)
    assert "outside the pack" in out


def test_a_symlinked_vanilla_override_leading_outside_the_pack_is_not_copied(
    tmp_path, pack, host
):
    _symlink_or_skip(
        pack / "vanilla/assets/mcme/textures/font/glyph.png", host / "id_ed25519"
    )

    output, out = _generate(tmp_path, pack)

    assert SECRET not in _published_bytes(output)
    assert "outside the pack" in out


def test_a_symlinked_version_folder_leading_outside_the_pack_is_not_copied(
    tmp_path, pack, host
):
    _symlink_or_skip(pack / "1_21_4", host)

    output, out = _generate(tmp_path, pack)

    assert SECRET not in _published_bytes(output)
    assert "outside the pack" in out


def test_a_symlinked_pack_png_leading_outside_the_pack_is_not_copied(
    tmp_path, pack, host
):
    _symlink_or_skip(pack / "pack.png", host / "id_ed25519")

    output, out = _generate(tmp_path, pack)

    assert SECRET not in _published_bytes(output)
    assert "outside the pack" in out


def test_a_symlinked_pack_mcmeta_leading_outside_the_pack_is_not_read(
    tmp_path, pack, host
):
    (host / "config.json").write_text(
        json.dumps({"pack": {"description": "HOST SECRET Sodium"}})
    )
    _symlink_or_skip(pack / "pack.mcmeta", host / "config.json")

    output, out = _generate(tmp_path, pack)

    assert SECRET not in _published_bytes(output)
    assert "outside the pack" in out


def test_a_symlinked_hardcoded_texture_leading_outside_the_pack_is_not_copied(
    tmp_path, pack, host
):
    _symlink_or_skip(
        pack / "assets/minecraft/textures/block/water_flow.png", host / "id_ed25519"
    )

    output, out = _generate(tmp_path, pack)

    assert SECRET not in _published_bytes(output)
    assert "outside the pack" in out


def test_a_symlink_that_stays_inside_the_pack_is_still_copied(tmp_path, pack):
    real = pack / "assets/mcme/textures/font/real.png"
    real.parent.mkdir(parents=True)
    real.write_bytes(b"GLYPH")
    _symlink_or_skip(pack / "assets/mcme/textures/font/alias.png", real)

    output, _ = _generate(tmp_path, pack)

    assert (output / "assets/mcme/textures/font/alias.png").read_bytes() == b"GLYPH"
