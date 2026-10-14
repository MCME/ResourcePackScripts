"""A Bedrock add-on that shows what Bedrock makes of generateBedrock's geometry.

    python generateBedrock/tools/testAddon.py <out.mcaddon> --vanilla <Vanilla-26.2> \\
        --pack Human=<RP-Human> --pack Mordor=<RP-Mordor>

Open the .mcaddon on a computer with Minecraft Bedrock: it imports a behavior
and a resource pack. Make a creative world with both, and every test case is
a block in the Construction tab named "MCME test: ...". No server and no
Geyser are involved: Geyser hands Bedrock the same geometry and materials, so
what these blocks show is what Geyser's players would see. Turn on the
Content Log (Settings > Creator) to see what Bedrock refuses.

The cases answer what no documentation does:

- Does a custom block draw a poly_mesh at all, and from which side?
- Does Bedrock draw block geometry beyond the 30 x 30 x 30 pixels Mojang
  documents, as cubes, as a poly_mesh, or not at all?
- Are the turned cubes' rotations and the textures' orientation right? The
  "compass" blocks carry N, E, S, W, U and D on the faces of those
  directions, readable from outside; the "plaque" blocks must look the same
  in each of their versions.
- Does tint_method tint by biome?

Each case is built in several versions (the geometry modes, oversize
handling, tint handling), so they can be compared side by side. docs/bedrock.md
("Checking a conversion in game") says what each should look like.
"""

import argparse
import json
import shutil
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import bedrock_settings  # noqa: E402
import blocks  # noqa: E402
import convert  # noqa: E402
import geometry  # noqa: E402
import mesh  # noqa: E402
import textures as texture_store  # noqa: E402
from java_pack import Assets  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

NAMESPACE = "mcme_test"
BP_UUID, BP_MODULE = "2f6b4e1a-7c3d-4b8e-9a51-0d2c6e8f4a13", "8a1d3c5e-2b4f-4e6a-9c7d-1f3e5a7b9c2d"
RP_UUID, RP_MODULE = "4c9e2a7d-1b3f-4d5e-8a6c-2e4f6a8c0b1d", "6e1a3c5b-7d9f-4b2e-8c4a-0e2d4f6b8a3c"
VERSION = [1, 0, 0]

# A version of a case: (label, geometry mode, oversize handling, tint)
HYBRID = ("hybrid", "hybrid", "keep", "biome")
POLYMESH = ("polymesh", "polymesh", "keep", "biome")
CUBES = ("cubes", "cubes", "keep", "biome")
OVERSIZE_POLY = ("oversize to polymesh", "hybrid", "polymesh", "biome")
CLIPPED = ("clipped", "hybrid", "clip", "biome")
BAKED = ("baked tint", "hybrid", "keep", "baked")


@dataclass
class Case:
    name: str
    pack: str | None  # the --pack it reads from, or None for a made-up one
    refs: list
    versions: list
    block_path: str = "stone"  # the Java block it stands for, for tints
    state: dict | None = None


CASES = [
    Case("goblin chandelier", "Mordor", [blocks.ModelRef("mcme:block/goblin_chandelier")], [HYBRID, POLYMESH, OVERSIZE_POLY, CLIPPED]),
    Case("catwalk 45", "Mordor", [blocks.ModelRef("mcme:block/catwalk_45_angled_3")], [HYBRID, POLYMESH, CLIPPED]),
    Case("spiked log", "Mordor", [blocks.ModelRef("mcme:block/spiked_log")], [HYBRID, POLYMESH, CUBES]),
    Case("animal skull 7", "Mordor", [blocks.ModelRef("mcme:block/animal_skull_7")], [HYBRID, POLYMESH]),
    Case("apple leaves", "Human", [blocks.ModelRef("mcme:block/apple_leaves")], [HYBRID, POLYMESH]),
    Case("white tree canopy", "Human", [blocks.ModelRef("mcme:block/white_tree_canopy")], [HYBRID, POLYMESH, CLIPPED]),
    Case("beech branch", "Human", [blocks.ModelRef("mcme:block/beech_branch_22.5_diagonal")], [HYBRID, POLYMESH, CUBES]),
    Case("oak leaves", "Human", [blocks.ModelRef("minecraft:block/oak_leaves")], [HYBRID, BAKED], "oak_leaves"),
    Case("oak stairs uvlock", "Human", [blocks.ModelRef("minecraft:block/oak_stairs", x=180, y=90, uvlock=True)], [HYBRID]),
    Case("oak stairs no uvlock", "Human", [blocks.ModelRef("minecraft:block/oak_stairs", x=180, y=90)], [HYBRID]),
]


# --------------------------------------------------------------------------
# Made-up models with letters, for the directions and the mirror
# --------------------------------------------------------------------------

# Letters as strokes on a 4 x 6 grid, y down
_LETTERS = {
    "N": [(0, 6, 0, 0), (0, 0, 4, 6), (4, 6, 4, 0)],
    "E": [(4, 0, 0, 0), (0, 0, 0, 6), (0, 6, 4, 6), (0, 3, 3, 3)],
    "S": [(4, 0, 0, 0), (0, 0, 0, 3), (0, 3, 4, 3), (4, 3, 4, 6), (4, 6, 0, 6)],
    "W": [(0, 0, 1, 6), (1, 6, 2, 2), (2, 2, 3, 6), (3, 6, 4, 0)],
    "U": [(0, 0, 0, 6), (0, 6, 4, 6), (4, 6, 4, 0)],
    "D": [(0, 0, 0, 6), (0, 6, 3, 6), (3, 6, 4, 4), (4, 4, 4, 2), (4, 2, 3, 0), (3, 0, 0, 0)],
    "F": [(0, 6, 0, 0), (0, 0, 4, 0), (0, 3, 3, 3)],
}
_COLOURS = {"N": (220, 40, 40), "S": (40, 120, 220), "E": (40, 170, 60), "W": (230, 170, 30), "U": (240, 240, 240), "D": (90, 90, 90), "F": (160, 60, 200)}


def letter_texture(letter: str) -> Image.Image:
    image = Image.new("RGBA", (64, 64), _COLOURS[letter] + (255,))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 63, 63), outline=(0, 0, 0, 255), width=2)
    for x0, y0, x1, y1 in _LETTERS[letter]:
        draw.line((14 + x0 * 9, 5 + y0 * 9, 14 + x1 * 9, 5 + y1 * 9), fill=(0, 0, 0, 255), width=6)
    # A marker in the texture's top-left corner shows turns the letter might hide
    draw.rectangle((3, 3, 10, 10), fill=(255, 255, 0, 255))
    return image


def compass_faces(inset: float) -> list[mesh.Face]:
    element = {
        "from": [inset, 0, inset],
        "to": [16 - inset, 16, 16 - inset],
        "faces": {d: {"texture": f"#{d}", "uv": [0, 0, 16, 16]} for d in mesh.DIRECTIONS},
    }
    textures = {d: f"{NAMESPACE}:letter/{d[0].upper()}" for d in mesh.DIRECTIONS}
    return mesh.element_faces(element, textures, True)


def plaque_faces() -> list[mesh.Face]:
    """A square tile with an F, turned about all three axes, facing mostly south."""
    turn = mesh.mat_mul(mesh.rotation("z", 25), mesh.mat_mul(mesh.rotation("y", 35), mesh.rotation("x", -20)))
    local = [(-5, -5, 0), (5, -5, 0), (5, 5, 0), (-5, 5, 0)]  # counter-clockwise from +z
    corners = tuple(mesh.add(mesh.mat_vec(turn, p), (8, 8, 8)) for p in local)
    uvs = ((0, 16), (16, 16), (16, 0), (0, 0))  # upright when looked at from the front
    return [mesh.Face(corners=corners, uvs=uvs, texture=f"{NAMESPACE}:letter/F")]


def triangle_faces() -> list[mesh.Face]:
    return [mesh.Face(corners=((2, 1, 8), (14, 1, 8), (8, 15, 8)), uvs=((0, 16), (16, 16), (8, 0)), texture=f"{NAMESPACE}:letter/F")]


MADE_UP = [
    ("compass full block", lambda: compass_faces(0), [HYBRID]),
    ("compass inset cube", lambda: compass_faces(0.5), [HYBRID]),
    ("plaque", plaque_faces, [HYBRID, POLYMESH]),
    ("triangle facing south", triangle_faces, [HYBRID]),
]


# --------------------------------------------------------------------------


class _LetterTextures(texture_store.TextureStore):
    """The made-up letter textures, beside the packs' own."""

    def __init__(self, assets, warn, letters_root):
        super().__init__(assets, warn)
        self.letters_root = letters_root

    def _load(self, texture):
        if texture.startswith(f"{NAMESPACE}:letter/"):
            path = self.letters_root / f"{texture.rsplit('/', 1)[1]}.png"
            return texture_store._Source(path, True, (64, 64), texture_store.OPAQUE, None)
        return super()._load(texture)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("output", help="The .mcaddon to write")
    parser.add_argument("--vanilla", required=True, help="The vanilla client resources (the folder that holds assets/)")
    parser.add_argument("--pack", action="append", default=[], metavar="NAME=PATH", help="A Java pack the cases read: Human=..., Mordor=...")
    args = parser.parse_args(argv)
    packs = dict(p.split("=", 1) for p in args.pack)

    work = Path(tempfile.mkdtemp(prefix="mcme-bedrock-test-"))
    letters = work / "letters"
    letters.mkdir()
    for letter in _LETTERS:
        letter_texture(letter).save(letters / f"{letter}.png")

    def warn(message):
        print(f"WARNING!!! {message}")

    rp, bp = work / "MCME Bedrock test RP", work / "MCME Bedrock test BP"
    stores, lang, made = {}, [], 0
    first_pack = next(iter(packs.values()), None)

    def store_for(pack_name):
        if pack_name not in stores:
            root = Path(packs[pack_name]) if pack_name else Path(first_pack or args.vanilla)
            assets = Assets(root, Path(args.vanilla), warn)
            stores[pack_name] = (assets, blocks.Models(assets, warn), _LetterTextures(assets, warn, letters))
        return stores[pack_name]

    cases = [(c.name, c.pack, c.refs, c.versions, c.block_path, c.state or {}) for c in CASES]
    cases += [(name, None, faces, versions, "stone", {}) for name, faces, versions in MADE_UP]
    for name, pack_name, source, versions, block_path, state in cases:
        if pack_name is not None and pack_name not in packs:
            print(f"Skipping {name}: no --pack {pack_name}=...")
            continue
        _, models, store = store_for(pack_name)
        if callable(source):
            faces = source()
        else:
            faces = []
            for ref in source:
                model = models.faces(ref)
                if model is None:
                    print(f"Skipping {name}: {ref.model} couldn't be read")
                    faces = []
                    break
                faces += model.faces
        for label, mode, oversize, tint in versions:
            built = geometry.build(faces, mode=mode, oversize=oversize)
            if built is None:
                print(f"Skipping {name} ({label}): nothing to draw")
                continue
            settings = bedrock_settings.Settings(geometry=mode, tint=tint, oversize=oversize)
            instances = convert.material_instances(built, store, settings, block_path, state)
            if instances is None:
                continue
            made += 1
            slug = convert._slug(f"{name}_{label}").replace(".", "_")
            identifier = f"{NAMESPACE}:{slug}"
            if built.full_block is not None:
                geometry_id = "minecraft:geometry.full_block"
            else:
                geometry_id = f"geometry.{NAMESPACE}.{slug}"
                content = json.loads(json.dumps(built.geometry))
                content["minecraft:geometry"][0]["description"]["identifier"] = geometry_id
                _write(rp / "models" / "blocks" / f"{slug}.geo.json", content)
            for instance in instances.values():
                # Behavior pack format 1.21.80 reads ambient occlusion as true or false
                instance["ambient_occlusion"] = instance["ambient_occlusion"] > 0
            _write(bp / "blocks" / f"{slug}.json", {
                "format_version": "1.21.80",
                "minecraft:block": {
                    "description": {"identifier": identifier, "menu_category": {"category": "construction"}},
                    "components": {
                        "minecraft:geometry": geometry_id,
                        "minecraft:material_instances": instances,
                        "minecraft:light_dampening": 0,
                    },
                },
            })
            notes = []
            if built.uses_poly_mesh:
                notes.append("poly_mesh")
            if built.oversize:
                notes.append("beyond 30 px")
            if built.dropped:
                notes.append(f"{built.dropped} faces clipped")
            lang.append(f"tile.{identifier}.name=MCME test: {name} ({label}){' - ' + ', '.join(notes) if notes else ''}")

    # One terrain atlas for everything the cases use
    merged_terrain, flipbooks = {}, []
    for _, _, store in stores.values():
        scratch = work / "store" / str(id(store))
        store.write(scratch, "MCME Bedrock test")
        for folder in ("textures",):
            src = scratch / folder
            if src.is_dir():
                shutil.copytree(src, rp / folder, dirs_exist_ok=True)
        terrain = json.loads((scratch / "textures" / "terrain_texture.json").read_text(encoding="utf-8"))
        merged_terrain.update(terrain["texture_data"])
        flip = scratch / "textures" / "flipbook_textures.json"
        if flip.is_file():
            flipbooks += json.loads(flip.read_text(encoding="utf-8"))
    _write(rp / "textures" / "terrain_texture.json", {
        "resource_pack_name": "MCME Bedrock test", "texture_name": "atlas.terrain",
        "padding": 8, "num_mip_levels": 4, "texture_data": merged_terrain,
    })
    if flipbooks:
        _write(rp / "textures" / "flipbook_textures.json", flipbooks)
    (rp / "texts").mkdir(parents=True, exist_ok=True)
    (rp / "texts" / "en_US.lang").write_text("\n".join(lang) + "\n", encoding="utf-8")
    _write(rp / "texts" / "languages.json", ["en_US"])

    _write(rp / "manifest.json", _manifest("MCME Bedrock test RP", RP_UUID, RP_MODULE, "resources", BP_UUID))
    _write(bp / "manifest.json", _manifest("MCME Bedrock test BP", BP_UUID, BP_MODULE, "data", RP_UUID))

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for root in (rp, bp):
            for path in sorted(root.rglob("*")):
                if path.is_file():
                    archive.write(path, f"{root.name}/{path.relative_to(root).as_posix()}")
    shutil.rmtree(work, ignore_errors=True)
    print(f"{made} test block(s) in {output}")
    return 0


def _manifest(name, header, module, kind, depends_on):
    return {
        "format_version": 2,
        "header": {"name": name, "description": "generateBedrock's test cases", "uuid": header,
                   "version": VERSION, "min_engine_version": [1, 21, 80]},
        "modules": [{"type": kind, "uuid": module, "version": VERSION}],
        "dependencies": [{"uuid": depends_on, "version": VERSION}],
    }


def _write(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, indent=1)


if __name__ == "__main__":
    sys.exit(main())
