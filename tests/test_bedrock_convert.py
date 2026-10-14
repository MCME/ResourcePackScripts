"""generateBedrock from a pack to Geyser's mappings: which blocks, which states, and what each gets.

The packs here are small ones built in a temporary folder, over a vanilla
folder that holds only what each test needs. The block list is the real one
(generateBedrock/java_blocks.json, 26.2).
"""

import json
from pathlib import Path

import bedrock_pack
import bedrock_settings
import blocks
import convert
import generateBedrock
import mesh
import pytest
import tints
from PIL import Image

JAVA_BLOCKS = Path(generateBedrock.HERE) / "java_blocks.json"


def png(path: Path, colour=(120, 120, 120, 255), size=(16, 16)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", size, colour).save(path)


def write(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")


CUBE_ALL = {"parent": "block/cube", "textures": {"particle": "#all", "down": "#all", "up": "#all",
                                                "north": "#all", "east": "#all", "south": "#all", "west": "#all"}}
CUBE = {"elements": [{"from": [0, 0, 0], "to": [16, 16, 16], "faces": {
    d: {"texture": f"#{d}", "cullface": d} for d in mesh.DIRECTIONS}}]}
LEAVES = {"elements": [{"from": [0, 0, 0], "to": [16, 16, 16], "faces": {
    d: {"texture": "#all", "tintindex": 0} for d in mesh.DIRECTIONS}}]}


@pytest.fixture
def vanilla(tmp_path):
    root = tmp_path / "vanilla"
    a = root / "assets" / "minecraft"
    write(a / "models/block/cube.json", CUBE)
    write(a / "models/block/cube_all.json", CUBE_ALL)
    for name in ("stone", "glowstone", "dirt"):
        write(a / f"blockstates/{name}.json", {"variants": {"": {"model": f"minecraft:block/{name}"}}})
        write(a / f"models/block/{name}.json", {"parent": "minecraft:block/cube_all", "textures": {"all": f"minecraft:block/{name}"}})
        png(a / f"textures/block/{name}.png")
    write(a / "blockstates/oak_leaves.json", {"variants": {"": {"model": "minecraft:block/oak_leaves"}}})
    write(a / "models/block/oak_leaves.json", {**LEAVES, "textures": {"all": "minecraft:block/oak_leaves"}})
    png(a / "textures/block/oak_leaves.png", (90, 90, 90, 255))
    return root


@pytest.fixture
def pack(tmp_path):
    root = tmp_path / "pack"
    write(root / "pack.mcmeta", {"pack": {"pack_format": 88, "description": "MCME Test"}})
    (root / "assets").mkdir()
    return root


def run(pack, vanilla, **settings):
    warnings = []
    converter = convert.Converter(pack, vanilla, bedrock_settings.Settings(**settings), "Test", JAVA_BLOCKS,
                                  warnings.append, lambda _: None).run()
    return converter, warnings


# --------------------------------------------------------------------------
# Which blocks are converted
# --------------------------------------------------------------------------


def test_a_vanilla_pack_converts_nothing(pack, vanilla):
    converter, warnings = run(pack, vanilla)
    assert converter.mappings == {} and warnings == []


def test_a_retextured_block_becomes_a_full_block_with_the_packs_texture(pack, vanilla):
    png(pack / "assets/minecraft/textures/block/stone.png", (200, 10, 10, 255))
    converter, _ = run(pack, vanilla)
    assert list(converter.mappings) == ["minecraft:stone"]
    stone = converter.mappings["minecraft:stone"]
    # One state: no state_overrides, its components at the top
    assert stone["name"] == "mcme_test_stone" and "state_overrides" not in stone
    assert stone["geometry"] == "minecraft:geometry.full_block"
    assert stone["material_instances"]["up"]["texture"] == "java.minecraft.block.stone"
    assert stone["material_instances"]["*"]["render_method"] == "opaque"


def test_a_blockstate_the_same_as_vanillas_converts_nothing(pack, vanilla):
    write(pack / "assets/minecraft/blockstates/dirt.json", {"variants": {"": {"model": "minecraft:block/dirt"}}})
    converter, _ = run(pack, vanilla)
    assert converter.mappings == {}


def test_light_comes_from_the_java_block(pack, vanilla):
    png(pack / "assets/minecraft/textures/block/glowstone.png")
    converter, _ = run(pack, vanilla)
    glowstone = converter.mappings["minecraft:glowstone"]
    assert (glowstone["light_emission"], glowstone["light_dampening"]) == (15, 15)


def test_every_state_gets_an_override_keyed_as_geyser_reads_it(pack, vanilla):
    png(pack / "assets/minecraft/textures/block/oak_leaves.png", (10, 200, 10, 255))
    converter, _ = run(pack, vanilla)
    leaves = converter.mappings["minecraft:oak_leaves"]
    assert leaves["only_override_states"] is True
    overrides = leaves["state_overrides"]
    assert len(overrides) == 7 * 2 * 2
    # Properties in the game's own order, all of them
    assert "distance=1,persistent=false,waterlogged=false" in overrides
    assert overrides["distance=1,persistent=false,waterlogged=false"]["light_dampening"] == 1


# --------------------------------------------------------------------------
# Tints
# --------------------------------------------------------------------------


def test_foliage_is_tinted_by_biome(pack, vanilla):
    png(pack / "assets/minecraft/textures/block/oak_leaves.png", (100, 100, 100, 255))
    converter, _ = run(pack, vanilla)
    instance = next(iter(converter.mappings["minecraft:oak_leaves"]["state_overrides"].values()))["material_instances"]["*"]
    assert instance["tint_method"] == "default_foliage"
    assert instance["texture"] == "java.minecraft.block.oak_leaves"


def test_baked_tints_multiply_a_copy_of_the_texture(pack, vanilla, tmp_path):
    png(pack / "assets/minecraft/textures/block/oak_leaves.png", (255, 255, 255, 255))
    converter, _ = run(pack, vanilla, tint="baked")
    instance = next(iter(converter.mappings["minecraft:oak_leaves"]["state_overrides"].values()))["material_instances"]["*"]
    assert "tint_method" not in instance
    assert instance["texture"] == "java.minecraft.block.oak_leaves.tint_77ab2f"
    out = tmp_path / "out"
    converter.write(out, "MCME Test")
    with Image.open(out / "textures/java_tinted/77ab2f/minecraft/block/oak_leaves.png") as image:
        assert image.convert("RGBA").getpixel((0, 0)) == (0x77, 0xAB, 0x2F, 255)


def test_a_tintindex_on_a_block_java_doesnt_colour_stays_untinted():
    assert tints.tint("brown_mushroom_block", {}, 0) is None
    assert tints.tint("oak_leaves", {}, -1) is None
    assert tints.tint("birch_leaves", {}, 0) == ("method", tints.BIRCH)
    assert tints.tint("redstone_wire", {"power": "0"}, 0) == ("colour", 0x4C0000)
    assert tints.tint("pink_petals", {}, 0) is None and tints.tint("pink_petals", {}, 1) == ("method", tints.GRASS)


# --------------------------------------------------------------------------
# Blockstates
# --------------------------------------------------------------------------


def test_variant_keys_and_multipart_conditions_match_as_javas_do():
    variants = blocks.Blockstate({"variants": {
        "facing=north,half=top": {"model": "a"},
        "facing=north": {"model": "b"},
        "": {"model": "c"},
    }})
    assert variants.models({"facing": "north", "half": "top"})[0].model == "minecraft:a"
    assert variants.models({"facing": "north", "half": "bottom"})[0].model == "minecraft:b"
    assert variants.models({"facing": "east", "half": "top"})[0].model == "minecraft:c"

    parts = blocks.Blockstate({"multipart": [
        {"apply": {"model": "post"}},
        {"when": {"north": "true|tall"}, "apply": {"model": "north"}},
        {"when": {"OR": [{"east": "true"}, {"west": "true"}]}, "apply": {"model": "side"}},
        {"when": {"AND": [{"up": "true"}, {"facing": "!south"}]}, "apply": {"model": "cap"}},
    ]})
    models = lambda **state: [r.model.split(":")[1] for r in parts.models(state)]  # noqa: E731
    assert models(north="tall", east="false", west="false", up="false", facing="north") == ["post", "north"]
    assert models(north="false", east="false", west="true", up="true", facing="north") == ["post", "side", "cap"]
    assert models(north="false", east="false", west="false", up="true", facing="south") == ["post"]


def test_a_weighted_list_draws_its_first_model():
    blockstate = blocks.Blockstate({"variants": {"": [{"model": "a", "weight": 1}, {"model": "b", "weight": 9}]}})
    assert [r.model for r in blockstate.models({})] == ["minecraft:a"]
    assert blockstate.weighted_lists() == 1


def test_y90_turns_north_to_east_and_x90_turns_north_to_down():
    face = mesh.element_faces({"from": [0, 0, 0], "to": [16, 16, 16], "faces": {"north": {"texture": "#t"}}}, {"t": "a:t"}, True)
    assert _direction(mesh.rotate_faces(face, 0, 90, False)[0]) == "east"
    assert _direction(mesh.rotate_faces(face, 90, 0, False)[0]) == "down"
    assert _direction(mesh.rotate_faces(face, 270, 0, False)[0]) == "up"


def _direction(face):
    return next(name for name, n in mesh.NORMALS.items() if mesh.dot(face.normal(), n) > 0.999)


def test_uvlock_keeps_a_top_texture_where_it_lies_in_the_world():
    def top(uv):
        element = {"from": [0, 0, 0], "to": [16, 16, 16], "faces": {"up": {"texture": "#t", "uv": uv}}}
        return mesh.element_faces(element, {"t": "a:t"}, True)

    whole = top([0, 0, 16, 16])
    # Without uvlock the texture turns with the block
    assert mesh.rotate_faces(whole, 0, 90, False)[0].uvs == whole[0].uvs
    # With it, every world corner keeps its texture coordinate
    locked = mesh.rotate_faces(whole, 0, 90, True)[0]
    for corner, uv in zip(locked.corners, locked.uvs):
        before = next(u for c, u in zip(whole[0].corners, whole[0].uvs) if mesh.length(mesh.sub(c, corner)) < 1e-6)
        assert uv == pytest.approx(before)
    # A part of the texture is turned about the texture's centre, as Java's uvlock turns it
    quarter = mesh.rotate_faces(top([0, 0, 8, 8]), 0, 90, True)[0]
    us, vs = {round(u) for u, _ in quarter.uvs}, {round(v) for _, v in quarter.uvs}
    assert len(us) == len(vs) == 2 and max(us) - min(us) == max(vs) - min(vs) == 8
    assert (us, vs) != ({0, 8}, {0, 8})


# --------------------------------------------------------------------------
# .obj models
# --------------------------------------------------------------------------

QUAD_OBJ = """mtllib leaves.mtl
v 0 0 0.5
v 1 0 0.5
v 1 1 0.5
v 0 1 0.5
v 0.5 0 0
v 0.5 1 0
v 0.5 0.5 1
vt 0 0
vt 1 0
vt 1 1
vt 0 1
usemtl m
f 1/1 2/2 3/3 4/4
f 5/1 6/2 7/3
"""


def _obj_pack(pack):
    models = pack / "assets/mcme/models/block"
    write(models / "leaves.obj", QUAD_OBJ)
    write(models / "leaves.mtl", "newmtl m\nmap_Kd mcme:block/leaves\n")
    write(models / "leaves.json", {"parent": "special-model-loader:builtin/obj", "model": "mcme:models/block/leaves.obj", "flip_v": True})
    png(pack / "assets/mcme/textures/block/leaves.png", (0, 200, 0, 255))
    write(pack / "assets/minecraft/blockstates/stone.json", {"variants": {"": {"model": "mcme:block/leaves", "y": 90}}})


def test_an_obj_model_becomes_cubes_and_a_poly_mesh(pack, vanilla, tmp_path):
    _obj_pack(pack)
    converter, warnings = run(pack, vanilla)
    assert warnings == []
    stone = converter.mappings["minecraft:stone"]
    assert stone["geometry"] == "geometry.mcme_test.leaves_y90"
    converter.write(tmp_path / "out", "MCME Test")
    geometry = json.loads((tmp_path / "out/models/blocks/mcme_test/leaves_y90.geo.json").read_text())
    bone = geometry["minecraft:geometry"][0]["bones"][0]
    assert len(bone["cubes"]) == 1 and len(bone["poly_mesh"]["polys"]) == 1
    assert geometry["format_version"] == "1.12.0"
    assert stone["material_instances"]["*"]["texture"] == "java.mcme.block.leaves"


def test_cubes_mode_needs_no_poly_mesh(pack, vanilla, tmp_path):
    _obj_pack(pack)
    converter, _ = run(pack, vanilla, geometry="cubes")
    converter.write(tmp_path / "out", "MCME Test")
    geometry = json.loads((tmp_path / "out/models/blocks/mcme_test/leaves_y90.geo.json").read_text())
    assert "poly_mesh" not in geometry["minecraft:geometry"][0]["bones"][0]


def test_a_missing_texture_leaves_the_state_to_bedrock_with_a_warning(pack, vanilla):
    write(pack / "assets/minecraft/blockstates/stone.json", {"variants": {"": {"model": "minecraft:block/odd"}}})
    write(pack / "assets/minecraft/models/block/odd.json", {"parent": "minecraft:block/cube_all", "textures": {"all": "minecraft:block/nowhere"}})
    converter, warnings = run(pack, vanilla)
    assert "minecraft:stone" not in converter.mappings
    assert warnings == ["Missing texture file: minecraft:block/nowhere"]


def test_a_face_names_its_texture_with_or_without_the_hash():
    faces = mesh.element_faces({"from": [0, 0, 0], "to": [16, 16, 16], "faces": {
        "up": {"texture": "1"}, "down": {"texture": "#1"}}}, {"1": "#0", "0": "a:b"}, True)
    assert [f.texture for f in faces] == ["a:b", "a:b"]


# --------------------------------------------------------------------------
# Textures
# --------------------------------------------------------------------------


def test_an_animated_texture_becomes_a_flipbook(pack, vanilla, tmp_path):
    texture = pack / "assets/minecraft/textures/block/stone.png"
    image = Image.new("RGBA", (16, 48))
    for frame, colour in enumerate([(255, 0, 0, 255), (0, 255, 0, 255), (0, 0, 255, 255)]):
        image.paste(Image.new("RGBA", (16, 16), colour), (0, frame * 16))
    texture.parent.mkdir(parents=True, exist_ok=True)
    image.save(texture)
    write(Path(str(texture) + ".mcmeta"), {"animation": {"frametime": 2, "frames": [0, {"index": 2, "time": 4}]}})
    converter, _ = run(pack, vanilla)
    converter.write(tmp_path / "out", "MCME Test")
    [flipbook] = json.loads((tmp_path / "out/textures/flipbook_textures.json").read_text())
    assert flipbook == {"flipbook_texture": "textures/java/minecraft/block/stone", "atlas_tile": "java.minecraft.block.stone",
                        "ticks_per_frame": 2, "frames": [0, 2, 2]}


def test_transparent_textures_choose_the_render_method(pack, vanilla):
    png(pack / "assets/minecraft/textures/block/stone.png", (10, 10, 10, 0))
    png(pack / "assets/minecraft/textures/block/dirt.png", (10, 10, 10, 128))
    converter, _ = run(pack, vanilla)
    assert converter.mappings["minecraft:stone"]["material_instances"]["*"]["render_method"] == "alpha_test_single_sided"
    assert converter.mappings["minecraft:dirt"]["material_instances"]["*"]["render_method"] == "blend"


# --------------------------------------------------------------------------
# Settings, the manifest and the command line
# --------------------------------------------------------------------------


def test_a_bad_setting_keeps_its_default_and_says_so(pack):
    write(pack / ".mcme-bedrock.json", {"geometry": "triangles", "tint": "baked", "baked_colours": {"grass": "#123456", "sky": "#000000"}})
    warnings = []
    settings = bedrock_settings.load(pack, warnings.append)
    assert (settings.geometry, settings.tint) == ("hybrid", "baked")
    assert settings.baked_colours[tints.GRASS] == 0x123456
    assert len(warnings) == 2


def test_the_pack_keeps_its_uuids_from_release_to_release():
    assert bedrock_pack.pack_uuids("Human") == bedrock_pack.pack_uuids("Human")
    assert bedrock_pack.pack_uuids("Human") != bedrock_pack.pack_uuids("Mordor")
    assert bedrock_pack.version_from_tag("v4.1.3") == [4, 1, 3]
    assert bedrock_pack.version_from_tag("v0.6") == [0, 6, 0]
    assert bedrock_pack.version_from_tag("test") == [0, 0, 1]


def test_the_command_writes_a_pack_and_the_mappings(pack, vanilla, tmp_path, capsys):
    png(pack / "assets/minecraft/textures/block/stone.png")
    png(pack / "pack.png")
    out = tmp_path / "out"
    status = generateBedrock.main([str(pack), str(out), str(vanilla), "--name", "Test", "--tag", "v1.2.3",
                                   "--mappings", str(tmp_path / "Test-Geyser.json"), "--mcpack", str(tmp_path / "Test.mcpack")])
    assert status == 0
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["header"]["version"] == [1, 2, 3]
    assert manifest["header"]["uuid"] == bedrock_pack.pack_uuids("Test")[0]
    assert (out / "pack_icon.png").is_file()
    mappings = json.loads((tmp_path / "Test-Geyser.json").read_text())
    assert mappings["format_version"] == 1 and "minecraft:stone" in mappings["blocks"]
    assert (tmp_path / "Test.mcpack").is_file()
    assert "WARNING" not in capsys.readouterr().out


def test_a_pack_can_turn_the_conversion_off(pack, vanilla, tmp_path, capsys):
    write(pack / ".mcme-bedrock.json", {"enabled": False})
    out = tmp_path / "out"
    assert generateBedrock.main([str(pack), str(out), str(vanilla), "--name", "Test"]) == 0
    assert not out.exists()
    assert "turned off" in capsys.readouterr().out
