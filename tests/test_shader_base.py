"""The shader base: what each pack gets, and the checks that keep a pack loading.

The client resolves every #moj_import in every shader of every namespace on
loading a pack, used or not, and one it can't find drops all resource packs.
"""

import subprocess
import sys
from pathlib import Path

import fluid_signature
import pytest
import shader_base
from PIL import Image

SCRIPT = Path(__file__).resolve().parent.parent / "generateVanilla" / "generateVanilla.py"

TERRAIN_VSH = Path("assets/minecraft/shaders/core/terrain.vsh")
TEXT_VSH = Path("assets/minecraft/shaders/core/text.vsh")
SODIUM_VSH = Path("assets/sodium/shaders/blocks/block_layer_opaque.vsh")
HOOK = Path("assets/minecraft/shaders/include/mcme_hook_fragment_main.glsl")


def _write(path: Path, text=""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


@pytest.fixture
def pack(tmp_path):
    pack = tmp_path / "pack"
    (pack / "assets").mkdir(parents=True)
    return pack


def test_every_import_in_the_base_resolves():
    # Sodium's includes among them, which a client without Sodium lacks
    assert shader_base.unresolved_imports(shader_base.BASE_PATH) == []


def test_the_base_has_a_stub_for_every_hook_it_imports():
    hooks = {p for p in shader_base.base_files() if shader_base.is_hook(p)}
    assert {h.name for h in hooks} == {
        "mcme_hook_vertex_globals.glsl",
        "mcme_hook_vertex_main.glsl",
        "mcme_hook_vertex_end.glsl",
        "mcme_hook_fragment_globals.glsl",
        "mcme_hook_fragment_main.glsl",
    }


def test_a_pack_without_objmc_models_or_hooks_gets_only_the_shared_shaders(tmp_path, pack):
    out = tmp_path / "out"
    shader_base.apply([pack], out)
    shipped = {p.relative_to(out) for p in out.rglob("*") if p.is_file()}
    assert shipped == shader_base.ALWAYS


def test_a_pack_with_objmc_models_gets_the_whole_base(tmp_path, pack):
    _write(pack / "assets/mcme/models/block/thing.obj")
    out = tmp_path / "out"
    shader_base.apply([pack], out)
    for relative in shader_base.base_files():
        assert (out / relative).read_bytes() == (shader_base.BASE_PATH / relative).read_bytes()


def test_a_pack_hook_is_kept_and_brings_the_terrain_shaders(tmp_path, pack):
    _write(pack / HOOK, "color.rgb *= 0.5;\n")
    out = tmp_path / "out"
    _write(out / HOOK, "color.rgb *= 0.5;\n")  # copied over with the pack's assets
    shader_base.apply([pack], out)
    assert (out / HOOK).read_text() == "color.rgb *= 0.5;\n"
    assert (out / TERRAIN_VSH).is_file()
    assert (out / SODIUM_VSH).is_file()


@pytest.mark.parametrize("owned", [TERRAIN_VSH, TEXT_VSH, SODIUM_VSH])
def test_a_pack_shipping_a_base_file_is_refused(tmp_path, pack, owned):
    _write(pack / "vanilla" / owned)
    with pytest.raises(shader_base.ShaderBaseError, match="owns"):
        shader_base.apply([pack, pack / "vanilla"], tmp_path / "out")


def test_an_import_nothing_provides_is_reported(pack):
    _write(
        pack / SODIUM_VSH,
        "#moj_import <sodium:globals.glsl>\n"
        "#moj_import <minecraft:fog.glsl>\n"  # vanilla's own
        "// #moj_import <commented_out.glsl>\n"
        "/* #moj_import <commented_out.glsl> */\n",
    )
    assert shader_base.unresolved_imports(pack) == [
        "assets/sodium/shaders/blocks/block_layer_opaque.vsh:1: sodium:globals.glsl"
    ]


def test_an_import_resolves_in_its_own_namespace_beside_or_by_default(pack):
    _write(pack / "assets/sodium/shaders/include/globals.glsl")
    _write(pack / "assets/minecraft/shaders/include/mine.glsl")
    _write(pack / "assets/sodium/shaders/blocks/local.glsl")
    _write(
        pack / SODIUM_VSH,
        "#moj_import <sodium:globals.glsl>\n"
        "#moj_import <mine.glsl>\n"
        '#moj_import "local.glsl"\n',
    )
    assert shader_base.unresolved_imports(pack) == []


def _texture(path: Path, size=(16, 32), alpha=180):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", size, (40, 90, 200, alpha)).save(path)


def test_finishing_a_pack_with_the_base_signs_its_water_and_only_its_water(tmp_path, pack):
    _write(pack / "assets/mcme/models/block/thing.obj")
    out = tmp_path / "out"
    textures = out / fluid_signature.FOLDER
    _texture(textures / "water_still.png")
    _texture(textures / "lava_still.png", alpha=255)
    shader_base.apply([pack], out)
    shader_base.finish(out)
    assert fluid_signature.is_signed(Image.open(textures / "water_still.png"), 2)
    assert not fluid_signature.is_signed(Image.open(textures / "lava_still.png"), 0)


def test_signing_changes_no_colour_by_more_than_3_and_no_alpha(tmp_path):
    path = tmp_path / "water.png"
    _texture(path)
    before = Image.open(path).convert("RGBA")
    after = before.copy()
    fluid_signature.sign(after, 3)
    assert fluid_signature.is_signed(after, 3)
    assert not fluid_signature.is_signed(after, 2)  # each sprite its own code
    for old, new in zip(before.getdata(), after.getdata()):
        assert all(abs(o - n) <= 3 for o, n in zip(old[:3], new[:3]))
        assert old[3] == new[3]


def test_a_water_texture_that_cant_carry_codes_warns_but_builds(tmp_path, pack, capsys):
    _write(pack / "assets/mcme/models/block/thing.obj")
    out = tmp_path / "out"
    _texture(out / fluid_signature.FOLDER / "water_still.png", size=(10, 16))
    shader_base.apply([pack], out)
    shader_base.finish(out)
    assert "10 wide, not a multiple of 4" in capsys.readouterr().out


def _generate(tmp_path, pack):
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(pack), str(tmp_path / "out"), str(tmp_path / "rp")],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )


def test_generate_vanilla_adds_the_base(tmp_path, pack):
    _write(pack / "assets/mcme/models/block/thing.obj")
    result = _generate(tmp_path, pack)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / "out" / TERRAIN_VSH).is_file()


def test_generate_vanilla_stops_on_a_pack_with_its_own_base_file(tmp_path, pack):
    _write(pack / "vanilla" / TERRAIN_VSH)
    result = _generate(tmp_path, pack)
    assert result.returncode != 0
    assert "terrain.vsh" in result.stderr


def test_generate_vanilla_stops_on_an_import_that_does_not_resolve(tmp_path, pack):
    _write(pack / "assets/mcme/shaders/core/thing.fsh", "#moj_import <sodium:fog.glsl>\n")
    result = _generate(tmp_path, pack)
    assert result.returncode != 0
    assert "mcme/shaders/core/thing.fsh:1: sodium:fog.glsl" in result.stderr
