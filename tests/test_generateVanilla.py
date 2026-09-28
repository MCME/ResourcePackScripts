"""End-to-end tests of generateVanilla.py's copying, run as the script it is.

The generated pack is published, so nothing a symlink in the input pack points
at outside that pack may end up in it - and an imperfect pack must not stop the
whole run. The runs here point at an empty vanilla pack, so there are no
blockstates or items to convert and only the copying stages have work to do.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import symlink_or_skip

SCRIPT = Path(__file__).resolve().parent.parent / "generateVanilla" / "generateVanilla.py"

SECRET = b"HOST SECRET"


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
    symlink_or_skip(pack / "assets/mcme/textures/font/glyph.png", host / "id_ed25519")

    output, out = _generate(tmp_path, pack)

    assert SECRET not in _published_bytes(output)
    assert "outside the pack" in out


def test_a_symlinked_folder_leading_outside_the_pack_is_not_copied(
    tmp_path, pack, host
):
    symlink_or_skip(pack / "assets/mcme/textures/font", host)

    output, out = _generate(tmp_path, pack)

    assert SECRET not in _published_bytes(output)
    assert "outside the pack" in out


def test_a_symlinked_assets_folder_leading_outside_the_pack_is_not_copied(
    tmp_path, pack, host
):
    (pack / "assets").rmdir()
    symlink_or_skip(pack / "assets", host)

    output, out = _generate(tmp_path, pack)

    assert SECRET not in _published_bytes(output)
    assert "outside the pack" in out


def test_a_symlinked_vanilla_override_leading_outside_the_pack_is_not_copied(
    tmp_path, pack, host
):
    symlink_or_skip(
        pack / "vanilla/assets/mcme/textures/font/glyph.png", host / "id_ed25519"
    )

    output, out = _generate(tmp_path, pack)

    assert SECRET not in _published_bytes(output)
    assert "outside the pack" in out


def test_a_symlinked_version_folder_leading_outside_the_pack_is_not_copied(
    tmp_path, pack, host
):
    symlink_or_skip(pack / "1_21_4", host)

    output, out = _generate(tmp_path, pack)

    assert SECRET not in _published_bytes(output)
    assert "outside the pack" in out


def test_a_symlinked_pack_png_leading_outside_the_pack_is_not_copied(
    tmp_path, pack, host
):
    symlink_or_skip(pack / "pack.png", host / "id_ed25519")

    output, out = _generate(tmp_path, pack)

    assert SECRET not in _published_bytes(output)
    assert "outside the pack" in out


def test_a_symlinked_pack_mcmeta_leading_outside_the_pack_is_not_read(
    tmp_path, pack, host
):
    (host / "config.json").write_text(
        json.dumps({"pack": {"description": "HOST SECRET Sodium"}})
    )
    symlink_or_skip(pack / "pack.mcmeta", host / "config.json")

    output, out = _generate(tmp_path, pack)

    assert SECRET not in _published_bytes(output)
    assert "outside the pack" in out


def test_a_symlinked_hardcoded_texture_leading_outside_the_pack_is_not_copied(
    tmp_path, pack, host
):
    symlink_or_skip(
        pack / "assets/minecraft/textures/block/water_flow.png", host / "id_ed25519"
    )

    output, out = _generate(tmp_path, pack)

    assert SECRET not in _published_bytes(output)
    assert "outside the pack" in out


def test_a_symlink_that_stays_inside_the_pack_is_still_copied(tmp_path, pack):
    real = pack / "assets/mcme/textures/font/real.png"
    real.parent.mkdir(parents=True)
    real.write_bytes(b"GLYPH")
    symlink_or_skip(pack / "assets/mcme/textures/font/alias.png", real)

    output, _ = _generate(tmp_path, pack)

    assert (output / "assets/mcme/textures/font/alias.png").read_bytes() == b"GLYPH"


# =========================================================================
# folders the pack does not have
# =========================================================================


def test_a_pack_without_a_vanilla_folder_is_still_generated(tmp_path, pack):
    (pack / "vanilla").rmdir()
    glyph = pack / "assets/mcme/textures/font/glyph.png"
    glyph.parent.mkdir(parents=True)
    glyph.write_bytes(b"GLYPH")

    output, out = _generate(tmp_path, pack)

    assert (output / "assets/mcme/textures/font/glyph.png").read_bytes() == b"GLYPH"
    assert "WARNING!!! Missing vanilla overrides folder" in out


def test_a_pack_without_an_assets_folder_is_still_generated(tmp_path, pack):
    (pack / "assets").rmdir()
    (pack / "pack.png").write_bytes(b"ICON")
    # copied after the assets, so it is only there if the run carried on
    (pack / "1_21_4").mkdir()
    (pack / "1_21_4" / "overlay.txt").write_text("overlay")

    output, out = _generate(tmp_path, pack)

    assert (output / "pack.png").read_bytes() == b"ICON"
    assert (output / "1_21_4" / "overlay.txt").read_text() == "overlay"
    assert "WARNING!!! Missing assets folder" in out
