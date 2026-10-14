"""From a Java block's states to the faces Bedrock should draw for each.

Geyser can give a Java block state a Bedrock custom block of its own (its
`custom_mappings`, "state_overrides"). A pack changes how a block looks with
its blockstate file, a model anywhere in a model's parent chain, or a
texture, so every block whose drawing the pack changes in any of these ways
gets one custom block per state the client draws from a model. Blocks the
pack leaves as vanilla stay Bedrock's own.

What can't come across:

- **Random variants.** A blockstate entry may list several models, one
  picked per position. A Bedrock custom block state has one look, so it takes
  the first, the entry the Lite variant also keeps.
- **States the client doesn't draw from a model**, like fluids, and models
  without elements, like a sign's: Bedrock draws those itself.
"""

import itertools
import json
import re
from dataclasses import dataclass
from pathlib import Path

import mesh
import yaml
from java_pack import MCME_NAMESPACE, Assets, full_identifier, split_identifier

# --------------------------------------------------------------------------
# The Java blocks: java_blocks.json, dumped from the game (tools/)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class StateFacts:
    light_emission: int
    light_dampening: int
    drawn_from_model: bool


@dataclass
class JavaBlock:
    identifier: str
    properties: dict[str, list[str]]  # in the order the game writes them
    default: StateFacts
    differing: dict[str, StateFacts]
    friction: float

    @property
    def path(self) -> str:
        return split_identifier(self.identifier)[1]

    def states(self):
        """Every state, as {property: value}, in the order of the properties' values."""
        names = list(self.properties)
        for values in itertools.product(*(self.properties[n] for n in names)):
            yield dict(zip(names, values))

    def key(self, state: dict[str, str]) -> str:
        """The state as Geyser's state_overrides key: "distance=1,persistent=false,..."."""
        return ",".join(f"{name}={state[name]}" for name in self.properties)

    def facts(self, state: dict[str, str]) -> StateFacts:
        return self.differing.get(self.key(state), self.default)


def load_java_blocks(path: Path) -> tuple[str, dict[str, JavaBlock]]:
    """(Minecraft version, identifier -> JavaBlock) from java_blocks.json."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    blocks = {}
    for identifier, entry in data["blocks"].items():
        blocks[identifier] = JavaBlock(
            identifier=identifier,
            properties=entry["properties"],
            default=StateFacts(*entry["default"]),
            differing={k: StateFacts(*v) for k, v in entry.get("states", {}).items()},
            friction=float(entry.get("friction", 0.6)),
        )
    return data["minecraft"], blocks


# --------------------------------------------------------------------------
# Blockstate files
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ModelRef:
    """One model a blockstate entry draws, and how it's turned."""

    model: str
    x: int = 0
    y: int = 0
    z: int = 0
    uvlock: bool = False


def _entry_model(entry) -> ModelRef | None:
    """The model a blockstate entry draws: the first of a weighted list."""
    if isinstance(entry, list):
        entry = entry[0] if entry else None
    if not isinstance(entry, dict) or not isinstance(entry.get("model"), str):
        return None
    try:
        return ModelRef(
            model=full_identifier(entry["model"]),
            x=int(entry.get("x", 0)) % 360,
            y=int(entry.get("y", 0)) % 360,
            z=int(entry.get("z", 0)) % 360,
            uvlock=entry.get("uvlock") is True,
        )
    except (TypeError, ValueError):
        return None


def _matches_value(wanted, actual: str) -> bool:
    """A condition's value: "a|b" for either, "!a" for anything but."""
    text = str(wanted).lower() if isinstance(wanted, bool) else str(wanted)
    negate = text.startswith("!")
    options = set(text.removeprefix("!").split("|"))
    return (actual in options) != negate


def _matches_when(when, state: dict[str, str]) -> bool:
    if not isinstance(when, dict):
        return True
    if "OR" in when:
        return any(_matches_when(w, state) for w in when["OR"])
    if "AND" in when:
        return all(_matches_when(w, state) for w in when["AND"])
    return all(name in state and _matches_value(value, state[name]) for name, value in when.items())


def _matches_variant(key: str, state: dict[str, str]) -> bool:
    if key in ("", "normal"):
        return True
    for pair in key.split(","):
        name, _, value = pair.partition("=")
        if state.get(name) != value:
            return False
    return True


class Blockstate:
    """A blockstate file: which models each state draws."""

    def __init__(self, data):
        self.variants = []
        self.parts = []
        if isinstance(data, dict) and isinstance(data.get("variants"), dict):
            self.variants = list(data["variants"].items())
        elif isinstance(data, dict) and isinstance(data.get("multipart"), list):
            self.parts = [(p.get("when"), p.get("apply")) for p in data["multipart"] if isinstance(p, dict)]

    def models(self, state: dict[str, str]) -> list[ModelRef]:
        if self.variants:
            for key, entry in self.variants:
                if _matches_variant(key, state):
                    ref = _entry_model(entry)
                    return [ref] if ref else []
            return []
        refs = []
        for when, apply in self.parts:
            if _matches_when(when, state):
                ref = _entry_model(apply)
                if ref:
                    refs.append(ref)
        return refs

    def all_models(self) -> set[str]:
        entries = [e for _, e in self.variants] + [a for _, a in self.parts]
        return {ref.model for ref in map(_entry_model, entries) if ref}

    def weighted_lists(self) -> int:
        """How many entries list several models (all but the first are left out)."""
        entries = [e for _, e in self.variants] + [a for _, a in self.parts]
        return sum(1 for e in entries if isinstance(e, list) and len(e) > 1)


# --------------------------------------------------------------------------
# Models
# --------------------------------------------------------------------------

_BUILTIN = re.compile(r"^(minecraft:)?builtin/")


@dataclass
class ModelFaces:
    faces: list[mesh.Face]
    from_pack: bool  # the model, a parent of it, or a texture it uses is the pack's
    obj: bool = False


class Models:
    """Model identifiers to faces, through parent chains and `.obj` files."""

    def __init__(self, assets: Assets, warn):
        self.assets = assets
        self.warn = warn
        self._faces: dict[str, ModelFaces | None] = {}
        self._turned: dict[ModelRef, ModelFaces | None] = {}
        self.multi_material_objs: set[str] = set()

    def faces(self, ref: ModelRef) -> ModelFaces | None:
        """The faces a blockstate entry draws, turned as it says."""
        if ref not in self._turned:
            base = self.model_faces(ref.model)
            if base is None:
                self._turned[ref] = None
            else:
                turned = mesh.rotate_faces(base.faces, ref.x, ref.y, ref.uvlock, ref.z)
                self._turned[ref] = ModelFaces(turned, base.from_pack, base.obj)
        return self._turned[ref]

    def model_faces(self, identifier: str) -> ModelFaces | None:
        if identifier not in self._faces:
            try:
                self._faces[identifier] = self._read(identifier)
            except mesh.ModelError as e:
                self.warn(f"Couldn't read model {identifier}: {e}")
                self._faces[identifier] = None
        return self._faces[identifier]

    def _read(self, identifier: str) -> ModelFaces | None:
        found = self.assets.model(identifier)
        if found is None:
            self.warn(f"Missing model file: {identifier}")
            return None
        path, from_pack = found
        data = self.assets.read_json(path)
        if not isinstance(data, dict):
            return None
        if isinstance(data.get("model"), str) and data["model"].endswith(".obj"):
            return self._read_obj(identifier, data)

        # A JSON model: textures merged down the chain, elements from the
        # nearest model that has them
        chain = [data]
        seen = {identifier}
        parent = data.get("parent")
        while isinstance(parent, str) and not _BUILTIN.match(parent):
            parent = full_identifier(parent)
            if parent in seen:
                self.warn(f"Model {identifier} has a parent loop through {parent}")
                break
            seen.add(parent)
            found = self.assets.model(parent)
            if found is None:
                self.warn(f"Missing model file: {parent} (a parent of {identifier})")
                break
            from_pack |= found[1]
            parent_data = self.assets.read_json(found[0])
            if not isinstance(parent_data, dict):
                break
            chain.append(parent_data)
            parent = parent_data.get("parent")

        textures: dict[str, str] = {}
        for model in reversed(chain):
            for name, value in (model.get("textures") or {}).items():
                if isinstance(value, str):
                    textures[name] = value if value.startswith("#") else full_identifier(value)
        elements = next((m["elements"] for m in chain if isinstance(m.get("elements"), list)), [])
        ambient_occlusion = next((m["ambientocclusion"] for m in chain if "ambientocclusion" in m), True)
        faces = []
        for element in elements:
            if isinstance(element, dict):
                faces += mesh.element_faces(element, textures, ambient_occlusion is not False)
        from_pack |= any(self._texture_from_pack(f.texture) for f in faces)
        return ModelFaces(faces, from_pack)

    def _texture_from_pack(self, texture: str) -> bool:
        found = self.assets.texture(texture)
        return bool(found and found[1])

    def _read_obj(self, identifier: str, data: dict) -> ModelFaces | None:
        """A Special Model Loader model, read as generateVanilla reads it."""
        namespace, model_path = split_identifier(identifier)
        obj_namespace, obj_ref = split_identifier(data["model"], MCME_NAMESPACE)
        if obj_namespace != MCME_NAMESPACE:
            self.warn(f"{identifier} names an .obj outside the mcme namespace - skipping it")
            return None
        # The .mtl and .objmeta are named after the model, or after the .obj
        # for a model outside the mcme namespace
        if namespace != MCME_NAMESPACE:
            model_path = obj_ref.removeprefix("models/").removesuffix(".obj")
        obj_file = self.assets.mcme_file(obj_ref)
        if obj_file is None:
            # generateVanilla skips such a model without a word; it's said here
            self.warn(f"Missing .obj file for {identifier}: {data['model']}")
            return None

        texture = None
        meta_file = self.assets.mcme_file(f"models/{model_path}.objmeta")
        if meta_file is not None:
            try:
                with open(meta_file, encoding="utf-8-sig") as f:
                    meta = yaml.safe_load(f) or {}
                if isinstance(meta, dict) and meta.get("texture"):
                    texture = str(meta["texture"])
            except (OSError, yaml.YAMLError) as e:
                self.warn(f"Couldn't read {model_path}.objmeta: {e}")
        if texture is None:
            mtl = model_path
            if isinstance(data.get("mtl_override"), str):
                _, mtl = split_identifier(data["mtl_override"], MCME_NAMESPACE)
                mtl = mtl.removeprefix("models/").removesuffix(".mtl")
            mtl_file = self.assets.mcme_file(f"models/{mtl}.mtl")
            if mtl_file is None:
                self.warn(f"Missing .mtl file for {identifier}: models/{mtl}.mtl")
                return None
            texture = _texture_from_mtl(mtl_file)
            if texture is None:
                self.warn(f"{mtl}.mtl names no texture (map_Kd), so {identifier} has none")
                return None
        texture = full_identifier(texture, MCME_NAMESPACE)

        try:
            text = obj_file.read_text(encoding="utf-8-sig", errors="replace")
            obj = mesh.read_obj(text, flip_v=data.get("flip_v") is True)
        except (OSError, ValueError, IndexError) as e:
            self.warn(f"Couldn't read the .obj of {identifier}: {e}")
            return None
        if len(obj.materials) > 1:
            self.multi_material_objs.add(identifier)
        return ModelFaces(mesh.obj_faces(obj, texture), True, obj=True)


def _texture_from_mtl(path: Path) -> str | None:
    with open(path, encoding="utf-8-sig", errors="replace") as f:
        for line in f:
            if line.startswith("map_Kd"):
                parts = line.split()
                if len(parts) > 1:
                    return parts[1].strip()
    return None
