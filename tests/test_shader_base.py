"""The shader base: what each pack gets, and the checks that keep a pack loading.

The client resolves every #moj_import in every shader of every namespace on
loading a pack, used or not, and one it can't find drops all resource packs.
"""

import json
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
INCLUDE = Path("assets/minecraft/shaders/include")
LAVA = INCLUDE / "lava.glsl"
LAVA_CONFIG = INCLUDE / "lava_config.glsl"


def _write(path: Path, text=""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _config(pack: Path, **data):
    (pack / shader_base.CONFIG_NAME).write_text(json.dumps(data))


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


def test_every_module_has_its_files_and_their_imports_resolve_when_on(tmp_path):
    for name, module in shader_base.MODULES.items():
        files = {p.name for p in shader_base.module_files(name)}
        assert set(module.imports) <= files
        pack = tmp_path / name
        (pack / "assets").mkdir(parents=True)
        _config(pack, modules=[name])
        shader_base.sync(pack)
        assert shader_base.unresolved_imports(pack) == []


def test_every_pack_gets_the_whole_base_and_no_module(tmp_path, pack):
    out = tmp_path / "out"
    shader_base.apply([pack], out)
    for relative in shader_base.base_files():
        if relative != shader_base.MODULES_FILE:
            assert (out / relative).read_bytes() == (shader_base.BASE_PATH / relative).read_bytes()
    assert not (out / LAVA).exists()
    assert "#define" not in (out / shader_base.MODULES_FILE).read_text()


def test_only_the_lite_zip_defines_mcme_lite(tmp_path, pack):
    _config(pack, modules=["lava"])
    shader_base.apply([pack], tmp_path / "full")
    shader_base.apply([pack], tmp_path / "lite", lite=True)
    assert "#define MCME_LITE" not in (tmp_path / "full" / shader_base.LITE_FILE).read_text().splitlines()
    assert "#define MCME_LITE" in (tmp_path / "lite" / shader_base.LITE_FILE).read_text().splitlines()
    # its fluids' files still ship: the pack's own shaders may import them
    assert (tmp_path / "lite" / LAVA).is_file()


def test_the_terrain_shaders_skip_fluids_in_lite():
    for shader in ("assets/minecraft/shaders/core/terrain.fsh", "assets/sodium/shaders/blocks/block_layer_opaque.fsh"):
        text = (shader_base.BASE_PATH / shader).read_text()
        assert "#moj_import <minecraft:mcme_lite.glsl>" in text
        lite = text.index("#ifdef MCME_LITE")
        assert text.index("int fluid = -1;", lite) < text.index("#else", lite) < text.index("fluidKind(", lite)


def test_a_pack_gets_the_modules_it_turns_on(tmp_path, pack):
    _config(pack, modules=["lava"])
    out = tmp_path / "out"
    shader_base.apply([pack], out)
    assert (out / LAVA).is_file()
    assert not (out / INCLUDE / "ice.glsl").exists()
    modules = (out / shader_base.MODULES_FILE).read_text()
    assert "#define MCME_MODULE_LAVA" in modules
    assert "#moj_import <minecraft:lava.glsl>" in modules
    assert shader_base.unresolved_imports(out) == []


def test_an_unknown_module_is_refused(tmp_path, pack):
    _config(pack, modules=["lavva"])
    with pytest.raises(shader_base.ShaderBaseError, match="no such module lavva"):
        shader_base.apply([pack], tmp_path / "out")


def test_a_pack_hook_is_kept(tmp_path, pack):
    _write(pack / HOOK, "color.rgb *= 0.5;\n")
    out = tmp_path / "out"
    _write(out / HOOK, "color.rgb *= 0.5;\n")  # copied over with the pack's assets
    shader_base.apply([pack], out)
    assert (out / HOOK).read_text() == "color.rgb *= 0.5;\n"
    assert (out / TERRAIN_VSH).is_file()
    assert (out / SODIUM_VSH).is_file()


def test_a_module_setting_the_pack_keeps_its_own_of_is_kept(tmp_path, pack):
    _config(pack, modules=["lava"], own=[LAVA_CONFIG.as_posix()])
    _write(pack / LAVA_CONFIG, "#define LAVA_HEAT 2.0\n")
    out = tmp_path / "out"
    _write(out / LAVA_CONFIG, "#define LAVA_HEAT 2.0\n")
    shader_base.apply([pack], out)
    assert (out / LAVA_CONFIG).read_text() == "#define LAVA_HEAT 2.0\n"


@pytest.mark.parametrize("owned", [TERRAIN_VSH, TEXT_VSH, SODIUM_VSH])
def test_a_pack_with_a_base_file_changed_by_hand_is_refused(tmp_path, pack, owned):
    _write(pack / "vanilla" / owned, "// changed\n")
    with pytest.raises(shader_base.ShaderBaseError, match="changed by hand"):
        shader_base.apply([pack, pack / "vanilla"], tmp_path / "out")


def test_an_unchanged_copy_of_the_base_is_fine_whatever_its_line_endings(tmp_path, pack):
    content = (shader_base.BASE_PATH / TERRAIN_VSH).read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    (pack / TERRAIN_VSH).parent.mkdir(parents=True)
    (pack / TERRAIN_VSH).write_bytes(content)
    shader_base.apply([pack], tmp_path / "out")


def test_sync_writes_the_base_into_the_pack_and_records_it(pack):
    _config(pack, modules=["lava"])
    shader_base.sync(pack)
    assert (pack / TERRAIN_VSH).is_file()
    assert (pack / LAVA).is_file()
    assert (pack / HOOK).is_file()
    lock = json.loads((pack / shader_base.LOCK_NAME).read_text())
    assert lock["modules"] == ["lava"]
    assert LAVA.as_posix() in lock["files"]
    assert HOOK.as_posix() not in lock["files"]  # the pack's own to fill
    assert shader_base.sync(pack) == []  # nothing more to do


def test_an_outdated_but_unchanged_synced_copy_is_replaced_by_the_build(tmp_path, pack):
    shader_base.sync(pack)
    old = "// the base as it was\n"
    _write(pack / TERRAIN_VSH, old)
    lock_path = pack / shader_base.LOCK_NAME
    lock = json.loads(lock_path.read_text())
    lock["files"][TERRAIN_VSH.as_posix()] = shader_base._digest(old.encode())
    lock_path.write_text(json.dumps(lock))
    out = tmp_path / "out"
    shader_base.apply([pack], out)
    assert (out / TERRAIN_VSH).read_bytes() == (shader_base.BASE_PATH / TERRAIN_VSH).read_bytes()


def test_sync_refuses_a_copy_changed_by_hand_unless_forced(pack):
    shader_base.sync(pack)
    _write(pack / TERRAIN_VSH, "// changed\n")
    with pytest.raises(shader_base.ShaderBaseError, match="changed by hand"):
        shader_base.sync(pack)
    shader_base.sync(pack, force=True)
    assert (pack / TERRAIN_VSH).read_bytes() == (shader_base.BASE_PATH / TERRAIN_VSH).read_bytes()


def test_sync_deletes_a_module_turned_off_but_keeps_the_hooks(pack):
    _config(pack, modules=["lava"])
    shader_base.sync(pack)
    _write(pack / HOOK, "color.rgb *= 0.5;\n")
    _config(pack, modules=[])
    shader_base.sync(pack)
    assert not (pack / LAVA).exists()
    assert (pack / HOOK).read_text() == "color.rgb *= 0.5;\n"


def _texture(path: Path, size=(16, 32), alpha=180):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", size, (40, 90, 200, alpha)).save(path)


def test_finishing_a_pack_signs_its_water_and_only_the_fluids_it_has_on(tmp_path, pack):
    out = tmp_path / "out"
    textures = out / fluid_signature.FOLDER
    _texture(textures / "water_still.png")
    _texture(textures / "lava_still.png", alpha=255)
    config = shader_base.apply([pack], out)
    shader_base.finish(out, config)
    assert fluid_signature.is_signed(Image.open(textures / "water_still.png"), 2)
    assert not fluid_signature.is_signed(Image.open(textures / "lava_still.png"), 0)


def _signed(kind, size=(16, 16), alpha=180):
    image = Image.new("RGBA", size, (40, 90, 200, alpha))
    fluid_signature.sign(image, kind)
    return image


def _flip(image, x, y):
    """Change the texel's code, not its look."""
    r, g, b, a = image.getpixel((x, y))
    image.putpixel((x, y), (r ^ 1, g, b, a))


def test_fluid_kinds_checks_a_blocks_chequerboard_as_fluid_glsl_does():
    water = _signed(2)
    assert fluid_signature.fluid_kinds(water) == {2}
    # every block of the sprite is broken on a texel fluidKind checks, x + y even...
    broken = water.copy()
    for y in range(0, 16, 4):
        for x in range(0, 16, 4):
            _flip(broken, x + 1, y + 1)
    assert fluid_signature.fluid_kinds(broken) == set()
    # ...or only on one it doesn't, x + y odd: still water
    odd = water.copy()
    for y in range(0, 16, 4):
        for x in range(0, 16, 4):
            _flip(odd, x + 1, y)
    assert fluid_signature.fluid_kinds(odd) == {2}


def test_fluid_kinds_wants_lava_opaque():
    assert fluid_signature.fluid_kinds(_signed(0, alpha=255)) == {0}
    assert fluid_signature.fluid_kinds(_signed(0, alpha=254)) == set()
    assert fluid_signature.fluid_kinds(Image.new("RGBA", (16, 16), (90, 90, 90, 255))) == set()


def test_finishing_refuses_a_texture_that_would_be_drawn_as_a_fluid(tmp_path, pack):
    out = tmp_path / "out"
    _texture(out / fluid_signature.FOLDER / "water_still.png")
    # a Special Model Loader model's texture copied from the signed water
    copy = out / "assets/mcme/textures/block/fountain.png"
    copy.parent.mkdir(parents=True)
    _signed(2).save(copy)
    config = shader_base.apply([pack], out)
    with pytest.raises(shader_base.ShaderBaseError, match="mcme/textures/block/fountain.png is taken for fluid kind 2"):
        shader_base.finish(out, config)
    copy.unlink()
    shader_base.finish(out, config)


def test_a_packs_own_fluid_textures_are_not_strays(pack):
    textures = pack / fluid_signature.FOLDER
    textures.mkdir(parents=True)
    _signed(6, alpha=255).save(textures / "powder_snow.png")
    assert fluid_signature.strays(pack, {"powder_snow": 6}) == []
    assert fluid_signature.strays(pack) == ["assets/minecraft/textures/block/powder_snow.png is taken for fluid kind 6"]
    assert fluid_signature.strays(pack, {"powder_snow": 7}) != []


def test_sync_signs_the_modules_and_the_packs_own_fluids(pack):
    textures = pack / fluid_signature.FOLDER
    _texture(textures / "lava_still.png", alpha=255)
    _texture(textures / "powder_snow.png", alpha=255)
    _config(pack, modules=["lava"], fluids={"powder_snow": 6})
    shader_base.sync(pack)
    assert fluid_signature.is_signed(Image.open(textures / "lava_still.png"), 0)
    assert fluid_signature.is_signed(Image.open(textures / "powder_snow.png"), 6)


def test_a_packs_own_fluid_must_be_kind_5_to_7(tmp_path, pack):
    _config(pack, fluids={"powder_snow": 2})
    with pytest.raises(shader_base.ShaderBaseError, match="kinds 5 to 7"):
        shader_base.apply([pack], tmp_path / "out")


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
    out = tmp_path / "out"
    _texture(out / fluid_signature.FOLDER / "water_still.png", size=(10, 16))
    config = shader_base.apply([pack], out)
    shader_base.finish(out, config)
    assert "10 wide, not a multiple of 4" in capsys.readouterr().out


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


def test_generate_vanilla_builds_a_synced_pack(tmp_path, pack):
    _config(pack, modules=["lava"])
    shader_base.sync(pack)
    result = _generate(tmp_path, pack)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / "out" / LAVA).is_file()
    assert not (tmp_path / "out" / shader_base.LOCK_NAME).exists()
    assert not (tmp_path / "out" / shader_base.CONFIG_NAME).exists()


def test_generate_vanilla_stops_on_a_pack_with_a_base_file_changed_by_hand(tmp_path, pack):
    _write(pack / "vanilla" / TERRAIN_VSH, "// changed\n")
    result = _generate(tmp_path, pack)
    assert result.returncode != 0
    assert "terrain.vsh" in result.stderr


def test_generate_vanilla_stops_on_an_import_that_does_not_resolve(tmp_path, pack):
    _write(pack / "assets/mcme/shaders/core/thing.fsh", "#moj_import <sodium:missing.glsl>\n")
    result = _generate(tmp_path, pack)
    assert result.returncode != 0
    assert "mcme/shaders/core/thing.fsh:1: sodium:missing.glsl" in result.stderr


def test_mark_for_sodium_lists_the_shaders_sodium_warns_about(pack):
    (pack / "pack.mcmeta").write_text('{\n  "pack": {"pack_format": 88, "description": "x"}\n}\n')
    _write(pack / TERRAIN_VSH)
    _write(pack / "assets/minecraft/shaders/include/fog.glsl")
    _write(pack / TEXT_VSH)
    assert shader_base.mark_for_sodium(pack)
    data = json.loads((pack / "pack.mcmeta").read_text())
    assert data["sodium"]["ignored_shaders"] == ["fog.glsl", "terrain.vsh"]
    assert data["pack"]["pack_format"] == 88
    assert (pack / "pack.mcmeta").read_text().startswith('{\n  "pack"')
    assert not shader_base.mark_for_sodium(pack)


def test_mark_for_sodium_keeps_what_the_pack_listed(pack):
    (pack / "pack.mcmeta").write_text(json.dumps({"pack": {}, "sodium": {"ignored_shaders": ["light.glsl"]}}))
    _write(pack / TERRAIN_VSH)
    shader_base.mark_for_sodium(pack)
    assert json.loads((pack / "pack.mcmeta").read_text())["sodium"]["ignored_shaders"] == ["light.glsl", "terrain.vsh"]


def test_mark_for_sodium_leaves_a_pack_without_terrain_shaders(pack):
    (pack / "pack.mcmeta").write_text('{"pack": {}}')
    _write(pack / TEXT_VSH)
    assert not shader_base.mark_for_sodium(pack)
    assert (pack / "pack.mcmeta").read_text() == '{"pack": {}}'


# --- 26.3 ----------------------------------------------------------------------

OVERLAY_SHADERS = shader_base.OVERLAY / shader_base.SHADERS_PATH


def test_an_include_for_26_3_loses_its_version_and_imports_by_include():
    text = shader_base.to_26_3("#version 330\n#moj_import <fog.glsl>\n#moj_import <minecraft:water.glsl>\nfloat x;\n", "minecraft/shaders/include/a.glsl")
    lines = text.splitlines()
    assert shader_base.TRANSLATED.split("{")[0] in lines[0]
    assert lines[1:] == ["#ifndef MCME_A_GLSL", "#define MCME_A_GLSL",
                         "#include <minecraft:fog.glsl>", "#include <minecraft:water.glsl>", "float x;", "#endif"]


def test_a_core_shader_for_26_3_keeps_its_version_and_numbers_its_inputs_and_outputs():
    vertex = shader_base.to_26_3("#version 330\nin vec3 Position;\nout float a;\nflat out vec3 b;\n", "minecraft/shaders/core/sky.vsh")
    assert vertex.splitlines()[0] == "#version 330"
    assert shader_base.SEPARATE_SHADERS in vertex
    assert "layout(location = 0) in vec3 Position;" in vertex
    assert "layout(location = 1) flat out vec3 b;" in vertex
    # the fragment shader's inputs at its vertex shader's outputs, by name
    fragment = shader_base.to_26_3("#version 330\nflat in vec3 b;\nin float a;\nout vec4 fragColor;\n", "minecraft/shaders/core/sky.fsh", {"a": 0, "b": 1})
    assert "layout(location = 1) flat in vec3 b;" in fragment
    assert "layout(location = 0) in float a;" in fragment
    assert "layout(location = 0) out vec4 fragColor;" in fragment


def test_sync_writes_26_3_copies_and_points_26_3_at_them(pack):
    (pack / "pack.mcmeta").write_text(json.dumps({"pack": {"pack_format": 88, "description": "x"}}))
    _write(pack / INCLUDE / "mcme_hook_vertex_globals.glsl", "#version 330\nflat out vec3 eye;\n")
    _write(pack / INCLUDE / "mcme_hook_fragment_globals.glsl", "#version 330\nflat in vec3 eye;\n")
    _write(pack / "assets/minecraft/shaders/core/sky.vsh", "#version 330\n#moj_import <minecraft:fog.glsl>\nin vec3 Position;\nout float a;\n")
    shader_base.sync(pack)
    terrain = (shader_base.BASE_PATH / shader_base.OVERLAY / TERRAIN_VSH).read_text()
    first = max(int(l) for l, kind, _, _ in shader_base.shader_check.LOCATED.findall(terrain) if kind == "out") + 1
    assert (pack / shader_base.OVERLAY / TERRAIN_VSH).read_text() == terrain
    assert f"layout(location = {first}) flat out vec3 eye;" in (pack / OVERLAY_SHADERS / "include/mcme_hook_vertex_globals.glsl").read_text()
    assert f"layout(location = {first}) flat in vec3 eye;" in (pack / OVERLAY_SHADERS / "include/mcme_hook_fragment_globals.glsl").read_text()
    sky = (pack / OVERLAY_SHADERS / "core/sky.vsh").read_text()
    assert "#include <minecraft:fog.glsl>" in sky and "layout(location = 0) out float a;" in sky
    mcmeta = json.loads((pack / "pack.mcmeta").read_text())
    assert mcmeta["pack"]["max_format"] == shader_base.OVERLAY_FORMAT
    assert {"min_format": shader_base.OVERLAY_FORMAT, "max_format": shader_base.OVERLAY_FORMAT,
            "directory": shader_base.OVERLAY.name} in mcmeta["overlays"]["entries"]
    assert shader_base.unresolved_includes(pack) == []


def test_sync_keeps_a_26_3_copy_written_by_hand_and_drops_one_no_longer_taken(pack):
    _write(pack / "assets/minecraft/shaders/core/sky.vsh", "#version 330\nin vec3 Position;\n")
    hand = pack / OVERLAY_SHADERS / "core/sky.vsh"
    _write(hand, "#version 330\n// by hand\n")
    stale = pack / OVERLAY_SHADERS / "include/gone.glsl"
    _write(stale, shader_base.TRANSLATED.format(path="minecraft/shaders/include/gone.glsl") + "\n")
    shader_base.sync(pack)
    assert hand.read_text() == "#version 330\n// by hand\n"
    assert not stale.exists()
