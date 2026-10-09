"""The shader base every pack's shaders are built on.

The terrain, objmc and Sodium shaders that make objmc models show - with or
without Sodium - with the water they draw, and the shaders every pack shares
(the action bar's text.vsh, fog.glsl) live once, in this repository's
shaderBase/. Every pack gets all of it. Modules - lava, ice - only the packs
that turn them on, in a .mcme-shaders.json at the top of their repository. A
pack adds features of its own through the base's hooks (mcme_hook_*.glsl),
never by changing a base file: changed copies drift apart, which is how the
packs came to break each other.

The base reaches a pack two ways. syncShaderBase.py writes it into the pack's
repository, so that a zip made straight from the repository has it - the
release scripts on the server don't add it. And the build adds it again
(apply), so a pack built with these scripts has the newest base. Both refuse
a pack whose copy of a base file was changed by hand: .mcme-shaders.lock,
written by the sync, records each file as it wrote it.

From 26.3 the game compiles its shaders to SPIR-V, which takes them written
otherwise (#include, a location on every input and output). The packs carry
26.3's copies in an overlay, mc26_3/, that pack.mcmeta points 26.3 at, over
assets/ - so one zip serves 26.2 and 26.3. The base's own hand-written ones
are in shaderBase/mc26_3; every include the game's shaders take - the base's,
its modules', the hooks and a pack's own - the sync and the build translate
(to_26_3), and a pack's own core shaders too.

shaderBase/ is a resource pack too, so it can be loaded below a pack checkout
to work on that pack's shaders without building it. See docs/shader-base.md.
"""

import hashlib
import json
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import fluid_signature
import shader_check

BASE_PATH = Path(__file__).resolve().parent.parent / "shaderBase"
MODULES_PATH = BASE_PATH / "modules"

CONFIG_NAME = ".mcme-shaders.json"
LOCK_NAME = ".mcme-shaders.lock"

HOOK_PATTERN = "mcme_hook_*.glsl"
HOOKS_PATH = Path("assets/minecraft/shaders/include")
# Which modules a pack turned on: written for each pack, from its config
MODULES_FILE = HOOKS_PATH / "mcme_modules.glsl"
LITE_FILE = HOOKS_PATH / "mcme_lite.glsl"


@dataclass(frozen=True)
class Module:
    define: str
    imports: tuple
    textures: tuple   # the fluid textures it draws over, to sign


MODULES = {
    "lava": Module("MCME_MODULE_LAVA", ("lava_config.glsl", "lava.glsl"), fluid_signature.LAVA),
    "ice": Module("MCME_MODULE_ICE", ("ice_config.glsl", "ice.glsl"), fluid_signature.ICE),
}

# The includes vanilla 26.2 has of its own, which a pack shader may import
# without shipping
VANILLA_INCLUDES = {
    "animation_sprite.glsl",
    "chunksection.glsl",
    "dynamictransforms.glsl",
    "fog.glsl",
    "globals.glsl",
    "light.glsl",
    "matrix.glsl",
    "projection.glsl",
    "sample_lightmap.glsl",
}

SHADER_SUFFIXES = {".vsh", ".fsh", ".glsl"}

PACK_MCMETA = "pack.mcmeta"
# What Sodium 0.9 warns about in a pack's minecraft/shaders, by file name
# (its ResourcePackScanner): vanilla's terrain programs and their includes
SODIUM_FLAGGED = {
    "terrain.vsh", "terrain.fsh", "light.glsl", "fog.glsl",
    *(f"rendertype_{p}.{s}" for p in ("solid", "cutout_mipped", "cutout", "translucent", "tripwire")
      for s in ("vsh", "fsh", "json")),
}

# As vanilla's GlslPreprocessor reads it: <namespace:path>, <path> (minecraft)
# or "path" (beside the importing file)
MOJ_IMPORT = re.compile(r'#\s*moj_import\s*(?:"([^"\n]*)"|<([^>\n]*)>)')
# and 26.3's, through shaderc
INCLUDE = re.compile(r'#\s*include\s*(?:"([^"\n]*)"|<([^>\n]*)>)')

# 26.3's copies, and the resource pack formats 26.2 and 26.3 have
OVERLAY = Path(shader_check.OVERLAYS["26.3"])
OVERLAY_FORMAT = 97
OLDEST_FORMAT = 88
SHADERS_PATH = Path("assets/minecraft/shaders")
# The includes vanilla 26.3 adds, for its transparency passes and terrain
VANILLA_INCLUDES_26_3 = VANILLA_INCLUDES | {
    "oit.glsl", "oit_add_transmittance.glsl", "oit_common.glsl", "oit_depth_bounds.glsl",
    "oit_depth_sample.glsl", "oit_sample.glsl", "terrainglobals.glsl", "texture_sampling.glsl",
}
# An input or output declared without a location, as hooks declare theirs
VARYING = re.compile(r"^([ \t]*)((?:(?:flat|smooth|noperspective|centroid)[ \t]+)*)(in|out)"
                     r"([ \t]+\w+[ \t]+(\w+)[ \t]*(?:\[[^\]\n]*\])?[ \t]*;)", re.M)


class ShaderBaseError(Exception):
    pass


@dataclass
class Config:
    """A pack's .mcme-shaders.json."""

    modules: list = field(default_factory=list)   # names in MODULES
    own: list = field(default_factory=list)       # base or module files the pack keeps its own of, such as a module's settings
    fluids: dict = field(default_factory=dict)    # its own fluid textures to sign: name -> kind, 5 to 7


def load_config(pack_root) -> Config:
    """The pack's config; a pack without one turns no module on."""
    path = Path(pack_root) / CONFIG_NAME
    if not path.is_file():
        return Config()
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except ValueError as e:
        raise ShaderBaseError(f"{path} isn't valid JSON: {e}") from e
    config = Config(
        modules=list(data.get("modules", [])),
        own=[Path(p) for p in data.get("own", [])],
        fluids=dict(data.get("fluids", {})),
    )
    unknown = [m for m in config.modules if m not in MODULES]
    if unknown:
        raise ShaderBaseError(f"{path}: no such module {', '.join(unknown)} (there are {', '.join(MODULES)})")
    wrong = {n: k for n, k in config.fluids.items() if not (isinstance(k, int) and 5 <= k <= 7)}
    if wrong:
        raise ShaderBaseError(f"{path}: a pack's own fluids are kinds 5 to 7, not {wrong}")
    return config


def _files(root: Path) -> list[Path]:
    return sorted(p.relative_to(root) for p in (root / "assets").rglob("*") if p.is_file())


def base_files() -> list[Path]:
    """Every file the base owns, relative to its folder - hooks and its
    hand-written 26.3 copies included."""
    return _files(BASE_PATH) + [OVERLAY / p for p in _files(BASE_PATH / OVERLAY)]


def module_files(name) -> list[Path]:
    return _files(MODULES_PATH / name)


def all_owned() -> set[Path]:
    """Every file the base or any of its modules owns."""
    owned = set(base_files())
    for name in MODULES:
        owned.update(module_files(name))
    return owned


def is_hook(relative: Path) -> bool:
    return relative.parent == HOOKS_PATH and relative.match(HOOK_PATTERN)


def modules_glsl(modules) -> str:
    """The pack's mcme_modules.glsl: a define and the includes of each module."""
    lines = [
        "// The shader base's modules this pack has turned on, from its .mcme-shaders.json.",
        "// Written by ResourcePackScripts' generateVanilla/syncShaderBase.py: don't edit it.",
    ]
    for name in sorted(modules):
        module = MODULES[name]
        lines.append(f"#define {module.define}")
        lines += [f"#moj_import <minecraft:{i}>" for i in module.imports]
    return "\n".join(lines) + "\n"


# --- 26.3's copies ---------------------------------------------------------------

# The mark of every copy the sync and the build translate, on its first line
# (a shader stage's second, after its #version): one in a pack's overlay
# without it is the pack's own, written by hand, and left alone
TRANSLATED = "// 26.3's copy of assets/{path}, translated by ResourcePackScripts' shader_base.py: don't edit it."
# What 26.3's own core shaders all have, after their #version
SEPARATE_SHADERS = "#extension GL_ARB_separate_shader_objects : require"
VERSION_LINE = re.compile(r"^[ \t]*#[ \t]*version\b[^\n]*\n", re.M)
STAGE_SUFFIXES = (".vsh", ".fsh", ".vert", ".frag")


def _include(match) -> str:
    relative, identifier = match.groups()
    if relative is not None:
        return f'#include "{relative}"'
    namespace, _, path = identifier.strip().rpartition(":")
    return f"#include <{namespace or 'minecraft'}:{path}>"


def to_26_3(text: str, path: str, locations: dict = None) -> str:
    """The shader at assets/`path` as 26.3 takes it: #include for each
    #moj_import, and the inputs and outputs named in `locations` (name ->
    location) given theirs. An include loses its #version - shaderc refuses
    one past a shader's first line - and is guarded, as 26.3's are. A stage
    keeps it, gains the extension 26.3's have, and has its other inputs and
    outputs numbered in the order declared, inputs and outputs each after the
    last it gives itself (from 0, as vanilla's are); a fragment shader's
    inputs take `locations`, its vertex shader's outputs."""
    stage = path.endswith(STAGE_SUFFIXES)
    locations = locations or {}
    counters = {kind: 1 + max((int(l) for l, k, _, _ in shader_check.LOCATED.findall(_strip_comments(text)) if k == kind), default=-1)
                for kind in ("in", "out")}

    def place(match):
        indent, qualifiers, kind, rest, name = match.groups()
        location = locations.get(name) if kind == "in" or not stage else None
        if location is None:
            if not stage:
                return match.group(0)
            location = counters[kind]
            counters[kind] += 1
        return f"{indent}layout(location = {location}) {qualifiers}{kind}{rest}"

    text = VARYING.sub(place, MOJ_IMPORT.sub(_include, text))
    mark = TRANSLATED.format(path=path) + "\n"
    if not stage:
        guard = "MCME_" + re.sub(r"\W", "_", Path(path).name).upper()
        body = VERSION_LINE.sub("", text)
        return f"{mark}#ifndef {guard}\n#define {guard}\n{body}{'' if body.endswith(chr(10)) else chr(10)}#endif\n"
    version = VERSION_LINE.search(text)
    extra = mark + ("" if SEPARATE_SHADERS in text else SEPARATE_SHADERS + "\n")
    return text[:version.end()] + extra + text[version.end():] if version else extra + text


def _imported(text: str) -> list[str]:
    """The minecraft includes a shader imports, by file name."""
    text = _strip_comments(text)
    names = []
    for relative, identifier in MOJ_IMPORT.findall(text) + INCLUDE.findall(text):
        if relative:
            names.append(Path(relative).name)
        else:
            namespace, _, path = identifier.strip().rpartition(":")
            if (namespace or "minecraft") == "minecraft":
                names.append(path)
    return names


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace")


def is_translated(path: Path) -> bool:
    return path.is_file() and TRANSLATED.split("{")[0] in "\n".join(_read(path).splitlines()[:2])


def _outputs(text: str) -> dict:
    return {name: int(location) for location, kind, _, name in shader_check.LOCATED.findall(_strip_comments(text)) if kind == "out"}


def overlay_files(pack_path) -> dict[Path, bytes]:
    """26.3's copies, by path from the pack, translated from assets/ in the
    pack at `pack_path` as it is on disk with the base in it - but where its
    overlay has the base's or its own hand-written one: of its core shaders,
    of its Distant Horizons Blaze3D shaders that import (which 26.3's shaderc
    compiles, as it does Sodium's), and of the minecraft includes those and
    Sodium's take. The hooks' inputs and outputs are numbered after the base
    terrain's last."""
    pack_path = Path(pack_path)
    assets, overlay_assets = pack_path / "assets", pack_path / OVERLAY / "assets"
    shaders, overlay = pack_path / SHADERS_PATH, pack_path / OVERLAY / SHADERS_PATH

    def winning(relative):
        hand = overlay_assets / relative
        return hand if hand.is_file() and not is_translated(hand) else assets / relative

    # the stages: each vertex shader before its fragment shader, whose inputs
    # take its outputs' locations
    stages = sorted({p.relative_to(root) for root in (assets, overlay_assets)
                     for folder in ("minecraft/shaders/core", "distanthorizons/shaders")
                     for p in ((root / folder).rglob("*") if (root / folder).is_dir() else [])
                     if p.suffix in STAGE_SUFFIXES and (folder.endswith("core") or "blaze" in p.parts)},
                    key=lambda p: (p.parent.as_posix(), p.stem if p.parts[0] == "minecraft" else "", p.suffix in (".fsh", ".frag")))
    translated, outputs = {}, {}
    for relative in stages:
        source = winning(relative)
        key = (relative.parent, relative.stem if relative.parts[0] == "minecraft" else "")
        fragment = relative.suffix in (".fsh", ".frag")
        if source.is_relative_to(overlay_assets):
            if not fragment:
                outputs[key] = _outputs(_read(source))
            continue
        text = _read(source)
        copy = to_26_3(text, relative.as_posix(), outputs.get(key) if fragment else None)
        if not fragment:
            outputs[key] = _outputs(copy)
        # DH's: only those that need it, the rest as they are
        if relative.parts[0] == "minecraft" or MOJ_IMPORT.search(_strip_comments(text)) or VARYING.search(_strip_comments(text)):
            translated[OVERLAY / "assets" / relative] = copy.encode("utf-8")

    # what they reach, and Sodium's chunk shaders, through the overlay's
    # includes where it has them
    sodium = [Path("sodium/shaders/blocks") / p.name for p in sorted((assets / "sodium/shaders/blocks").glob("*"))]
    seeds = [winning(r) for r in stages + sodium]
    reached, queue = set(), [n for seed in seeds for n in _imported(_read(seed))]
    while queue:
        name = queue.pop()
        source = winning(Path("minecraft/shaders/include") / name)
        if name in reached or not source.is_file():
            continue
        reached.add(name)
        queue += _imported(_read(source))

    # the hooks' outputs and those of what they import, in order, after the base terrain's
    taken = outputs.get((Path("minecraft/shaders/core"), "terrain"), {}).values()
    names, seen, queue = [], set(), ["mcme_hook_vertex_globals.glsl"]
    while queue:
        name = queue.pop(0)
        source = shaders / "include" / name
        if name in seen or not source.is_file():
            continue
        seen.add(name)
        text = _strip_comments(_read(source))
        names += [m.group(5) for m in VARYING.finditer(text) if m.group(3) == "out" and m.group(5) not in names]
        queue += _imported(text)
    locations = {name: max(taken, default=-1) + 1 + i for i, name in enumerate(names)}

    for name in sorted(reached):
        relative = Path("minecraft/shaders/include") / name
        if winning(relative) == assets / relative:
            translated[OVERLAY / "assets" / relative] = to_26_3(_read(assets / relative), relative.as_posix(), locations).encode("utf-8")
    return translated


def mark_overlay(pack_root) -> bool:
    """Point 26.3 at the pack's overlay in pack.mcmeta, and give the pack the
    formats from 26.2's to 26.3's. Whether it changed the file."""
    path = Path(pack_root) / PACK_MCMETA
    if not path.is_file() or not (Path(pack_root) / OVERLAY).is_dir():
        return False
    text = path.read_text(encoding="utf-8-sig")
    data = json.loads(text)
    before = json.dumps(data, sort_keys=True)
    pack = data.setdefault("pack", {})
    pack.setdefault("min_format", min(pack.get("pack_format", OLDEST_FORMAT), OLDEST_FORMAT))
    if not isinstance(pack.get("max_format"), int) or pack["max_format"] < OVERLAY_FORMAT:
        pack["max_format"] = OVERLAY_FORMAT
    entries = data.setdefault("overlays", {}).setdefault("entries", [])
    entry = next((e for e in entries if e.get("directory") == OVERLAY.name), None)
    if entry is None:
        entries.append({"min_format": OVERLAY_FORMAT, "max_format": OVERLAY_FORMAT, "directory": OVERLAY.name})
    if json.dumps(data, sort_keys=True) == before:
        return False
    _write_mcmeta(path, text, data)
    return True


def _write_mcmeta(path: Path, text: str, data: dict):
    indent = re.match(r"\{\s*\n([ \t]+)", text)
    path.write_text(json.dumps(data, indent=indent.group(1) if indent else 4) + "\n", encoding="utf-8")


def translate(pack_path) -> list[str]:
    """Write 26.3's translated copies into the pack (overlay_files), and
    delete those an earlier one wrote that it no longer takes; what it did."""
    done = []
    translated = overlay_files(pack_path)
    for relative, content in translated.items():
        target = Path(pack_path) / relative
        if target.is_file() and _same(target.read_bytes(), content):
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        done.append(f"wrote {relative.as_posix()}")
    folder = Path(pack_path) / OVERLAY / "assets"
    for old in sorted(folder.rglob("*")) if folder.is_dir() else []:
        relative = old.relative_to(pack_path)
        if old.suffix in (*SHADER_SUFFIXES, *STAGE_SUFFIXES) and is_translated(old) and relative not in translated:
            old.unlink()
            done.append(f"deleted {relative.as_posix()}")
    return done


def shipped(config: Config) -> dict[Path, bytes]:
    """What the base gives the pack, as file contents by path: the base, the
    pack's modules and its mcme_modules.glsl - hooks and its own files aside."""
    files = {}
    for relative in base_files():
        files[relative] = (BASE_PATH / relative).read_bytes()
    for name in config.modules:
        for relative in module_files(name):
            files[relative] = (MODULES_PATH / name / relative).read_bytes()
    files[MODULES_FILE] = modules_glsl(config.modules).encode()
    return {r: c for r, c in files.items() if not is_hook(r) and r not in config.own}


def _same(a: bytes, b: bytes) -> bool:
    """The same text, whatever its line endings - git may have changed them."""
    return a.replace(b"\r\n", b"\n") == b.replace(b"\r\n", b"\n")


def _digest(content: bytes) -> str:
    return hashlib.sha256(content.replace(b"\r\n", b"\n")).hexdigest()


def read_lock(pack_root) -> dict[str, str]:
    path = Path(pack_root) / LOCK_NAME
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8")).get("files", {})


def changed_by_hand(asset_roots, config: Config, lock: dict[str, str]) -> list[Path]:
    """The pack's copies of base and module files that differ from the base's
    and from what the sync wrote: changed by hand, or never synced. An
    unchanged copy of an older base is fine; the newer one replaces it."""
    want = shipped(config)
    found = []
    for root in asset_roots:
        root = Path(root)
        for relative in sorted(all_owned() | {MODULES_FILE}):
            if is_hook(relative) or relative in config.own:
                continue
            path = root / relative
            if not path.is_file():
                continue
            content = path.read_bytes()
            if relative in want and _same(content, want[relative]):
                continue
            if lock.get(relative.as_posix()) == _digest(content):
                continue
            found.append(path)
    return found


def _check(asset_roots, pack_root, config: Config):
    found = changed_by_hand(asset_roots, config, read_lock(pack_root))
    if found:
        raise ShaderBaseError(
            "The pack's copies of these shader base files were changed by hand "
            "(ResourcePackScripts/shaderBase). Run syncShaderBase.py on the pack "
            "to put the base's back, and hook pack features in through "
            "mcme_hook_*.glsl instead, or list a module's settings it keeps its "
            f"own of under \"own\" in {CONFIG_NAME} - see docs/shader-base.md:\n"
            + "\n".join(f"  {p}" for p in found)
        )
    _check_own(pack_root, config)


def _check_own(pack_root, config: Config):
    missing = [r for r in config.own if not (Path(pack_root) / r).is_file()]
    if missing:
        raise ShaderBaseError(
            f"{CONFIG_NAME} says the pack has its own of these, but it hasn't:\n"
            + "\n".join(f"  {r.as_posix()}" for r in missing)
        )


def apply(asset_roots, output_path, lite=False) -> Config:
    """Add the base to the pack built from `asset_roots` into `output_path`.

    `asset_roots` are the pack's folders holding an assets/ that end up in the
    output - its root first, whose .mcme-shaders.json says which modules it
    has, and for the vanilla pack its vanilla/ overrides. The pack's hooks and
    its own files are kept; the base's empty hooks are added where it has none.
    With `lite`, for the Lite zip, mcme_lite.glsl defines MCME_LITE: no fluid
    is drawn by a shader, only the hooks' features (the fire eye) and the
    models' shaders run. Returns the pack's config, for finish().
    """
    pack_root = Path(asset_roots[0])
    config = load_config(pack_root)
    _check(asset_roots, pack_root, config)
    output_path = Path(output_path)
    for relative, content in shipped(config).items():
        target = output_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    for relative in base_files():
        target = output_path / relative
        if is_hook(relative) and not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(BASE_PATH / relative, target)
    if lite:
        lite_file = output_path / LITE_FILE
        lite_file.write_text(lite_file.read_text(encoding="utf-8") + "#define MCME_LITE\n", encoding="utf-8")
    return config


def sign(pack_path, config: Config, check=False) -> tuple[list[str], bool]:
    """Sign the pack's water, its modules' fluids and its own fluids."""
    messages, ok = fluid_signature.sign_pack(pack_path, fluid_signature.WATER, check)
    for name in config.modules:
        more, good = fluid_signature.sign_pack(pack_path, MODULES[name].textures, check)
        messages += more
        ok &= good
    if config.fluids:
        more, good = fluid_signature.sign_pack(pack_path, tuple(config.fluids), check, config.fluids)
        messages += more
        ok &= good
    return messages, ok


def sync(pack_root, force=False) -> list[str]:
    """Write the base and the pack's modules into its repository, sign its
    fluids, and record what was written in its .mcme-shaders.lock. Refuses a
    pack whose copies were changed by hand, unless forced - as for a pack's
    first sync, over the copies it kept before. Returns what was done."""
    pack_root = Path(pack_root)
    config = load_config(pack_root)
    lock = read_lock(pack_root)
    if not force:
        _check([pack_root], pack_root, config)
    done = []
    want = shipped(config)
    _check_own(pack_root, config)
    for relative, content in want.items():
        target = pack_root / relative
        if target.is_file() and target.read_bytes() == content:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        done.append(f"wrote {relative.as_posix()}")
    for relative in base_files():
        target = pack_root / relative
        if is_hook(relative) and not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(BASE_PATH / relative, target)
            done.append(f"wrote {relative.as_posix()} (an empty hook)")
    done += translate(pack_root)
    # what an earlier sync wrote that the pack no longer gets, such as a
    # module turned off - unless changed since
    for name, digest in lock.items():
        relative = Path(name)
        target = pack_root / relative
        if (relative not in want and relative not in config.own and not is_hook(relative)
                and target.is_file() and _digest(target.read_bytes()) == digest):
            target.unlink()
            done.append(f"deleted {name}")
    # and unchanged copies of modules the pack doesn't turn on
    for name in MODULES:
        if name in config.modules:
            continue
        for relative in module_files(name):
            target = pack_root / relative
            if (relative not in config.own and target.is_file()
                    and _same(target.read_bytes(), (MODULES_PATH / name / relative).read_bytes())):
                target.unlink()
                done.append(f"deleted {relative.as_posix()} (module {name} is off)")
    messages, ok = sign(pack_root, config)
    done += [m for m in messages if m.endswith("now")]
    if not ok:
        done += [f"WARNING: {m}" for m in messages if not m.endswith(("signed", "now"))]
    files = {r.as_posix(): _digest(c) for r, c in sorted(want.items())}
    record = {"base": _base_commit(), "modules": sorted(config.modules), "files": files}
    (pack_root / LOCK_NAME).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    if mark_for_sodium(pack_root):
        done.append(f"wrote {PACK_MCMETA}'s sodium.ignored_shaders")
    if mark_overlay(pack_root):
        done.append(f"wrote {PACK_MCMETA}'s overlay for 26.3")
    check_imports(pack_root)
    return done


def mark_for_sodium(pack_root) -> bool:
    """Tell Sodium, in pack.mcmeta, which of the shaders it warns about the
    pack has on purpose: the vanilla terrain shaders, and the includes only
    they use, which Sodium doesn't run - it runs the base's own, in the sodium
    namespace. Without this, Sodium flags every pack with the base as
    incompatible. Whether it changed the file."""
    path = Path(pack_root) / PACK_MCMETA
    shaders = Path(pack_root) / "assets/minecraft/shaders"
    if not path.is_file() or not shaders.is_dir():
        return False
    shipped = sorted({p.name for p in shaders.rglob("*") if p.is_file() and p.name in SODIUM_FLAGGED})
    text = path.read_text(encoding="utf-8-sig")
    data = json.loads(text)
    section = data.setdefault("sodium", {})
    listed = section.get("ignored_shaders", [])
    missing = [name for name in shipped if name not in listed]
    if not missing:
        return False
    section["ignored_shaders"] = listed + missing
    _write_mcmeta(path, text, data)
    return True


def _base_commit() -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(BASE_PATH), "log", "-1", "--format=%h", "--", "."],
            capture_output=True, text=True, check=True,
        ).stdout.strip() or "?"
    except (OSError, subprocess.CalledProcessError):
        return "?"


def _strip_comments(text: str) -> str:
    """The text with its comments blanked, keeping its lines where they were."""
    text = re.sub(r"/\*.*?\*/", lambda m: re.sub(r"[^\n]", " ", m.group()), text, flags=re.S)
    return re.sub(r"//[^\n]*", "", text)


def unresolved_imports(pack_path) -> list[str]:
    """Every #moj_import in the pack's shaders, in any namespace, that vanilla
    can't resolve against the pack and its own includes.

    Vanilla resolves them all whether a shader is used or not, and a single one
    missing fails the whole pack.
    """
    pack_path = Path(pack_path)
    assets = pack_path / "assets"
    missing = []
    for shader in sorted(assets.glob("*/shaders/**/*")):
        if shader.suffix not in SHADER_SUFFIXES or not shader.is_file():
            continue
        text = _strip_comments(shader.read_text(encoding="utf-8-sig", errors="replace"))
        for match in MOJ_IMPORT.finditer(text):
            relative, identifier = match.groups()
            if relative is not None:
                target = shader.parent / relative
                name = relative
                vanilla = False
            else:
                namespace, _, path = identifier.strip().rpartition(":")
                namespace = namespace or "minecraft"
                target = assets / namespace / "shaders/include" / path
                name = f"{namespace}:{path}"
                vanilla = namespace == "minecraft" and path in VANILLA_INCLUDES
            if not target.is_file() and not vanilla:
                line = text.count("\n", 0, match.start()) + 1
                missing.append(f"{shader.relative_to(pack_path).as_posix()}:{line}: {name}")
    return missing


def finish(pack_path, config: Config = None):
    """Once the pack is complete: sign its fluids (its water, and its modules'
    and its own, by its config), check that no other texture would be drawn
    as one, and that every shader import resolves."""
    pack_path = Path(pack_path)
    config = config or Config()
    messages, ok = sign(pack_path, config)
    if not ok:
        print(
            "WARNING!!! Fluid textures that can't carry the codes the shaders "
            "know them by, so they show plain:\n"
            + "\n".join(f"  {m}" for m in messages if not m.endswith(("signed", "now"))),
            flush=True,
        )
    strays = fluid_signature.strays(pack_path, config.fluids)
    if strays:
        raise ShaderBaseError(
            "Textures the terrain shaders would draw over as a fluid (water, lava...), "
            "though they aren't one - edit a few texels of each:\n" + "\n".join(f"  {s}" for s in strays)
        )
    mark_for_sodium(pack_path)
    if (pack_path / OVERLAY).is_dir():
        translate(pack_path)
        mark_overlay(pack_path)
    check_imports(pack_path)
    check_rules(pack_path)


def check_rules(pack_path):
    """No #version or #extension a platform lacks (shader_check); compiling
    every shader is checkShaders.py's, which needs glslang and the jars."""
    problems = shader_check.check_rules(pack_path)
    if problems:
        raise ShaderBaseError(
            "Shaders some players' drivers would refuse:\n" + "\n".join(f"  {p}" for p in problems)
        )


def unresolved_includes(pack_path) -> list[str]:
    """In the pack's 26.3 overlay, every #include of a minecraft include that
    neither it, the pack's assets/ nor vanilla 26.3 has, and every #moj_import
    left - 26.3 has none."""
    pack_path = Path(pack_path)
    overlay = pack_path / OVERLAY / SHADERS_PATH
    missing = []
    for shader in sorted(overlay.rglob("*")) if overlay.is_dir() else []:
        if shader.suffix not in SHADER_SUFFIXES or not shader.is_file():
            continue
        text = _strip_comments(_read(shader))
        where = shader.relative_to(pack_path).as_posix()
        for match in MOJ_IMPORT.finditer(text):
            missing.append(f"{where}:{text.count(chr(10), 0, match.start()) + 1}: #moj_import, which 26.3 doesn't have")
        for match in INCLUDE.finditer(text):
            relative, identifier = match.groups()
            namespace, _, name = (identifier or "").strip().rpartition(":")
            if relative is not None or (namespace or "minecraft") != "minecraft":
                continue
            if not ((overlay / "include" / name).is_file() or (pack_path / SHADERS_PATH / "include" / name).is_file()
                    or name in VANILLA_INCLUDES_26_3):
                missing.append(f"{where}:{text.count(chr(10), 0, match.start()) + 1}: minecraft:{name}")
    return missing


def check_imports(pack_path):
    missing = unresolved_imports(pack_path) + unresolved_includes(pack_path)
    if missing:
        raise ShaderBaseError(
            "Shader imports that don't resolve - the client would drop every "
            "resource pack on loading this one:\n"
            + "\n".join(f"  {m}" for m in missing)
        )
