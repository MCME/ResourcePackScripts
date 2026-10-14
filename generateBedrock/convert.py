"""The conversion: a Java pack into a Bedrock pack and Geyser's block mappings.

For every Java block whose drawing the pack changes (blocks.py), each state
the client draws from a model gets the faces of its models (mesh.py), turned
into Bedrock geometry (geometry.py), and a Geyser state override naming that
geometry and its materials. States whose models differ only in texture share
one geometry; a state that is one plainly textured whole cube uses Bedrock's
own full block, which Bedrock culls against its neighbours like a vanilla one.

Geyser takes a custom block's collision and selection boxes from the Java
block itself, so the mappings carry only what Bedrock needs to draw and light
it: geometry, materials, light emission and dampening (Bedrock lights the
world on the client), and friction.
"""

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import blocks
import geometry
import textures as texture_store
import tints
from bedrock_settings import Settings
from java_pack import Assets

# Java's friction for a block that doesn't set one; Bedrock's default is 1 minus it
DEFAULT_FRICTION = 0.6


@dataclass
class Report:
    minecraft: str = ""
    blocks: int = 0
    states: int = 0
    geometries: int = 0
    full_block_states: int = 0
    polymesh_geometries: int = 0
    approximated_faces: int = 0
    clipped: dict[str, int] = field(default_factory=dict)  # geometry -> faces left out
    oversize_kept: set[str] = field(default_factory=set)
    weighted_lists: int = 0
    biome_tinted: int = 0
    multi_material_objs: set[str] = field(default_factory=set)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9_.]+", "_", text.lower()).strip("_.") or "block"


def block_prefix(name: str) -> str:
    """The start of every custom block's name: Geyser registers it as geyser_custom:<name>."""
    return "mcme_" + _slug(name).replace(".", "_")


class Converter:
    def __init__(self, pack: Path, vanilla: Path, settings: Settings, name: str, java_blocks: Path, warn, debug):
        self.settings = settings
        self.warn = warn
        self.debug = debug
        self.assets = Assets(pack, vanilla, warn)
        self.models = blocks.Models(self.assets, warn)
        self.textures = texture_store.TextureStore(self.assets, warn)
        self.prefix = block_prefix(name)
        self.report = Report()
        self.report.minecraft, self.java_blocks = blocks.load_java_blocks(java_blocks)
        self._built: dict[tuple, geometry.BlockGeometry | None] = {}
        self._identifiers: dict[str, str] = {}  # geometry content -> identifier
        self.geometry_files: dict[str, dict] = {}  # identifier -> file content
        self.mappings: dict[str, dict] = {}

    # ----------------------------------------------------------------------

    def run(self):
        for identifier in sorted(self.java_blocks):
            mapping = self._block(self.java_blocks[identifier])
            if mapping is not None:
                self.mappings[identifier] = mapping
        self.report.blocks = len(self.mappings)
        self.report.geometries = len(self.geometry_files)
        self.report.multi_material_objs = set(self.models.multi_material_objs)
        return self

    def _changed(self, block: blocks.JavaBlock, path: Path, from_pack: bool, data) -> bool:
        """Whether the pack's blockstate file says something vanilla's doesn't."""
        if not from_pack:
            return False
        vanilla = self.assets.vanilla_blockstate(block.path)
        return vanilla is None or self.assets.read_json(vanilla) != data

    def _block(self, block: blocks.JavaBlock) -> dict | None:
        found = self.assets.blockstate(block.path)
        if found is None:
            return None
        path, from_pack = found
        data = self.assets.read_json(path)
        if data is None:
            return None
        blockstate = blocks.Blockstate(data)
        changed = self._changed(block, path, from_pack, data)
        if not changed:
            # Vanilla's blockstate: still converted when one of its models or
            # textures is the pack's
            uses_pack = False
            for model in blockstate.all_models():
                faces = self.models.model_faces(model)
                if faces is not None and faces.from_pack:
                    uses_pack = True
                    break
            if not uses_pack:
                return None
        self.report.weighted_lists += blockstate.weighted_lists()

        overrides = {}
        for state in block.states():
            facts = block.facts(state)
            if not facts.drawn_from_model:
                continue
            refs = tuple(blockstate.models(state))
            if not refs:
                continue
            built = self._geometry(block, refs)
            if built is None:
                continue
            entry = self._state_entry(block, state, facts, built)
            if entry is not None:
                overrides[block.key(state)] = entry
        if not overrides:
            return None
        self.report.states += len(overrides)
        self.debug(f"Bedrock block {block.identifier}: {len(overrides)} state(s)")

        mapping: dict = {"name": f"{self.prefix}_{_slug(block.path)}"}
        if not block.properties:
            # A block with one state is mapped as a whole, not through state_overrides
            mapping.update(overrides[""])
        else:
            mapping["only_override_states"] = True
            mapping["state_overrides"] = overrides
        return mapping

    def _geometry(self, block: blocks.JavaBlock, refs: tuple) -> tuple[geometry.BlockGeometry, str] | None:
        """(geometry, its identifier, or Bedrock's full block's) for the models a state draws."""
        if refs not in self._built:
            faces = []
            for ref in refs:
                model = self.models.faces(ref)
                if model is not None:
                    faces += model.faces
            built = geometry.build(
                faces,
                mode=self.settings.geometry,
                oversize=self.settings.oversize,
                reverse_poly_winding=self.settings.reverse_polymesh_winding,
            )
            self._built[refs] = built
            if built is not None:
                self._register(block, refs, built)
        built = self._built[refs]
        if built is None:
            return None
        if built.full_block is not None:
            return built, "minecraft:geometry.full_block"
        return built, self._identifiers[_content_key(built)]

    def _register(self, block: blocks.JavaBlock, refs: tuple, built: geometry.BlockGeometry):
        if built.full_block is not None:
            return
        key = _content_key(built)
        if key in self._identifiers:
            return
        hint = _slug(_ref_hint(refs[0]) if len(refs) == 1 else f"{block.path}_{len(self._identifiers)}")
        identifier = f"geometry.{self.prefix}.{hint}"
        n = 2
        while identifier in self.geometry_files:
            identifier = f"geometry.{self.prefix}.{hint}_{n}"
            n += 1
        content = json.loads(json.dumps(built.geometry))
        content["minecraft:geometry"][0]["description"]["identifier"] = identifier
        self._identifiers[key] = identifier
        self.geometry_files[identifier] = content
        if built.uses_poly_mesh:
            self.report.polymesh_geometries += 1
        self.report.approximated_faces += built.approximated
        # Reported by the models they're made of, not once per rotation
        sources = [r.model for r in refs] if len(refs) == 1 else [block.identifier]
        for source in sources:
            if built.dropped:
                self.report.clipped[source] = max(built.dropped, self.report.clipped.get(source, 0))
            if built.oversize:
                self.report.oversize_kept.add(source)

    def _state_entry(self, block, state, facts, built_and_id) -> dict | None:
        built, identifier = built_and_id
        instances = material_instances(built, self.textures, self.settings, block.path, state)
        if instances is None:
            return None  # the missing texture is reported already
        self.report.biome_tinted += sum(1 for i in instances.values() if "tint_method" in i)

        entry = {
            "geometry": identifier,
            "material_instances": instances,
            "light_emission": facts.light_emission,
            "light_dampening": facts.light_dampening,
        }
        if abs(block.friction - DEFAULT_FRICTION) > 1e-6:
            entry["friction"] = round(min(0.9, max(0.0, 1 - block.friction)), 4)
        if built.full_block is not None:
            self.report.full_block_states += 1
        return entry

    # ----------------------------------------------------------------------

    def write(self, root: Path, pack_name: str):
        root = Path(root)
        for identifier, content in self.geometry_files.items():
            name = identifier.removeprefix(f"geometry.{self.prefix}.")
            target = root / "models" / "blocks" / self.prefix / f"{name}.geo.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "w", encoding="utf-8", newline="\n") as f:
                json.dump(content, f, separators=(",", ":"))
        self.textures.write(root, pack_name)

    def mappings_file(self) -> dict:
        return {"format_version": 1, "blocks": self.mappings}


def material_instances(built: geometry.BlockGeometry, textures, settings: Settings, block_path: str, state: dict) -> dict | None:
    """A state's material instances, as Geyser's mappings write them, or None for a missing texture.

    Java tints a face by its block (tints.py): by biome through Bedrock's
    tint_method, or baked into a copy of the texture. Every material of the
    state draws with the most see-through render method any of them needs.
    """
    materials = built.materials()
    if any(textures.source(m.texture) is None for m in materials.values()):
        return None
    instances, methods = {}, []
    for name, material in materials.items():
        how = tints.tint(block_path, state, material.tintindex)
        colour = method = None
        if how and how[0] == "colour":
            colour = how[1]
        elif how and settings.tint == "baked":
            colour = settings.baked_colours[how[1]]
        elif how:
            method = how[1]
        instance = {
            "texture": textures.use(material.texture, colour),
            "face_dimming": material.shade,
            "ambient_occlusion": 1.0 if material.ambient_occlusion else 0.0,
        }
        if method:
            instance["tint_method"] = method
        instances[name] = instance
        methods.append(textures.render_method(material.texture))
    render_method = max(methods, key=texture_store.RENDER_ORDER.index)
    for instance in instances.values():
        instance["render_method"] = render_method
    return instances


def _content_key(built: geometry.BlockGeometry) -> str:
    return json.dumps(built.geometry, sort_keys=True)


def _ref_hint(ref: blocks.ModelRef) -> str:
    _, path = ref.model.split(":", 1)
    hint = path.removeprefix("block/").replace("/", ".")
    for axis in "xyz":
        if getattr(ref, axis):
            hint += f"_{axis}{getattr(ref, axis)}"
    if ref.uvlock and (ref.x or ref.y or ref.z):
        hint += "_uvlock"
    return hint


def summary_lines(report: Report) -> list[tuple[str, str]]:
    """(kind, text) lines for the end of a run: "info" or "warning"."""
    lines = [
        ("info", f"Bedrock: {report.blocks} block(s), {report.states} state(s), {report.geometries} geometr{'y' if report.geometries == 1 else 'ies'}"
                 f" ({report.polymesh_geometries} with a poly_mesh), {report.full_block_states} state(s) as Bedrock full blocks"),
    ]
    if report.weighted_lists:
        lines.append(("info", f"Bedrock: {report.weighted_lists} blockstate entr{'y lists' if report.weighted_lists == 1 else 'ies list'} several models; Bedrock draws the first of each"))
    if report.approximated_faces:
        lines.append(("info", f"Bedrock: {report.approximated_faces} face(s) that aren't textured rectangles are drawn as the rectangle around them"))
    if report.biome_tinted:
        lines.append(("info", f"Bedrock: {report.biome_tinted} material(s) are tinted by biome (tint_method), which Geyser passes on only once its mappings reader reads tint_method (docs/bedrock.md)"))
    if report.clipped:
        names = sorted(report.clipped, key=lambda k: -report.clipped[k])
        shown = ", ".join(n.split(":", 1)[-1] for n in names[:5])
        more = f" and {len(names) - 5} more" if len(names) > 5 else ""
        faces = sum(report.clipped.values())
        lines.append(("warning", f"Bedrock: {len(names)} model(s) are bigger than Bedrock lets a block be (30x30x30 pixels, with the block's own cell), so up to {faces} of their faces are left out on Bedrock: {shown}{more}"))
    if report.oversize_kept:
        names = sorted(report.oversize_kept)
        shown = ", ".join(n.split(":", 1)[-1] for n in names[:5]) + (f" and {len(names) - 5} more" if len(names) > 5 else "")
        lines.append(("info", f"Bedrock: {len(names)} model(s) reach beyond the 30x30x30 pixels Mojang documents for a block and are kept whole: {shown}"))
    if report.multi_material_objs:
        names = sorted(report.multi_material_objs)
        shown = ", ".join(names[:5]) + (f" and {len(names) - 5} more" if len(names) > 5 else "")
        lines.append(("warning", f"Bedrock: {len(names)} .obj model(s) use several materials, but only the .mtl's first texture is drawn, as for the Vanilla variant: {shown}"))
    return lines
