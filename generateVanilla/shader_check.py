"""Checks a pack's shaders before players get them (docs/shader-base.md).

A shader that doesn't compile on one player's driver drops every resource
pack they have on, and nobody here tests every GPU. So a pack's shaders are
checked here, each a way a driver could refuse them:

- rules: no #version above 410 (macOS stops at OpenGL 4.1) and no #extension
  but the few every platform has (ALLOWED_EXTENSIONS);
- compile: every shader the pack has, its imports filled in as the game
  fills them, through glslang - the reference compiler, stricter than most
  drivers - and, with moderngl, compiled and linked to the shader it runs
  with on a real driver (Mesa's, in CI);
- Distant Horizons: each of the pack's DH overrides against DH's own shader
  of the same name, which the override replaces outright - an input,
  output or uniform DH has that the override lacks means DH changed it since
  the override was written.

The shaders a pack doesn't have, and the includes its own import, come from
the game's and the mods' jars: the ones installed in .minecraft, or the
versions in shader_versions.json, downloaded (fetch_jars). Only CI needs those.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

VERSIONS_PATH = Path(__file__).resolve().parent / "shader_versions.json"

# macOS has OpenGL 4.1 core and nothing later
MAX_VERSION = 410
# What a shader may #extension: core on every platform the game runs on
ALLOWED_EXTENSIONS = {
    # DH's own Blaze3D shaders require it; core in OpenGL 4.1, so on macOS too
    "GL_ARB_separate_shader_objects",
}

STAGES = {".vsh": "vert", ".vert": "vert", ".fsh": "frag", ".frag": "frag"}
SHADER_SUFFIXES = set(STAGES) | {".glsl"}

# The defines the game and Sodium compile these with, every combination used
DEFINES = {
    ("minecraft", "core/terrain"): [[], ["ALPHA_CUTOUT 0.5"]],
    ("sodium", "blocks/block_layer_opaque"): [
        ["USE_VERTEX_COMPRESSION", "USE_FOG"],
        ["USE_VERTEX_COMPRESSION", "USE_FOG", "ALPHA_CUTOUT 0.5"],
        ["USE_VERTEX_COMPRESSION"],
    ],
}
# DH's post-processing programs (OpenGL renderer) without a vertex shader of their own
DH_SHARED_VERTEX = "shared/gl/quad_apply.vert"
# The game's full-screen programs (lightmap, blit_screen) without one either
MINECRAFT_SHARED_VERTEX = "core/screenquad.vsh"

MOJ_IMPORT = re.compile(r'^[ \t]*#[ \t]*moj_import[ \t]*(?:"([^"\n]*)"|<([^>\n]*)>)', re.M)
VERSION = re.compile(r"^[ \t]*#[ \t]*version[ \t]+(\d+)([ \t]+\w+)?", re.M)
EXTENSION = re.compile(r"^[ \t]*#[ \t]*extension[ \t]+(\w+)", re.M)

JAR_IDS = ("minecraft", "sodium", "distanthorizons")
MODRINTH = {"sodium": "sodium", "distanthorizons": "distanthorizons", "iris": "iris"}
NAMES = {"minecraft": "Minecraft", "sodium": "Sodium", "distanthorizons": "Distant Horizons", "iris": "Iris"}


@dataclass
class Report:
    problems: list = field(default_factory=list)
    notes: list = field(default_factory=list)


def strip_comments(text: str) -> str:
    """The text with its comments blanked, keeping its lines where they were."""
    text = re.sub(r"/\*.*?\*/", lambda m: re.sub(r"[^\n]", " ", m.group()), text, flags=re.S)
    return re.sub(r"//[^\n]*", "", text)


# --- where shaders come from -------------------------------------------------

def _jar_id(path: Path):
    """minecraft for the game's client jar, the mod's id for a Fabric mod, else None."""
    try:
        with zipfile.ZipFile(path) as z:
            names = set(z.namelist())
            if "fabric.mod.json" in names:
                return json.loads(z.read("fabric.mod.json").decode("utf-8", "replace"), strict=False).get("id")
            if "version.json" in names and "net/minecraft/client/Minecraft.class" in names:
                return "minecraft"
    except (OSError, zipfile.BadZipFile, ValueError):
        pass
    return None


def jar_version(path: Path) -> str:
    with zipfile.ZipFile(path) as z:
        if "fabric.mod.json" in z.namelist():
            version = json.loads(z.read("fabric.mod.json").decode("utf-8", "replace"), strict=False)["version"]
        else:
            version = json.loads(z.read("version.json"))["id"]
    return version.split("+")[0]


def find_jars(minecraft_version: str) -> dict:
    """The game's and the mods' jars installed in .minecraft: id -> path."""
    root = Path(os.path.expandvars(r"%APPDATA%/.minecraft")) if os.name == "nt" else Path.home() / ".minecraft"
    found = {}
    client = root / "versions" / minecraft_version / f"{minecraft_version}.jar"
    if client.is_file():
        found["minecraft"] = client
    for folder in (root / "iris-reserved" / minecraft_version, root / "mods"):
        for jar in sorted(folder.glob("*.jar")) if folder.is_dir() else []:
            jar_id = _jar_id(jar)
            if jar_id in JAR_IDS and jar_id not in found:
                found[jar_id] = jar
    return found


def _get(url: str):
    request = urllib.request.Request(url, headers={"User-Agent": "MCME/ResourcePackScripts (shader check)"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def _modrinth_versions(project: str, minecraft_version: str) -> list:
    query = urllib.parse.urlencode({"loaders": '["fabric"]', "game_versions": f'["{minecraft_version}"]'})
    return [v for v in json.loads(_get(f"https://api.modrinth.com/v2/project/{project}/version?{query}"))
            if v["version_type"] == "release"]


def _is_version(entry: dict, version: str) -> bool:
    return version in re.split(r"[-+]", entry["version_number"])


def latest_versions(minecraft_version: str) -> dict:
    """The newest release of the game and of each mod for that game version."""
    manifest = json.loads(_get("https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"))
    latest = {"minecraft": manifest["latest"]["release"]}
    for jar_id, project in MODRINTH.items():
        releases = _modrinth_versions(project, minecraft_version)
        if releases:
            number = releases[0]["version_number"]
            latest[jar_id] = next((t for t in re.split(r"[-+]", number) if re.fullmatch(r"\d+(\.\d+)+", t)
                                   and t != minecraft_version), number)
    return latest


def fetch_jars(versions: dict, cache: Path) -> dict:
    """Downloads the game's client jar and Sodium's and DH's at these versions."""
    cache.mkdir(parents=True, exist_ok=True)
    minecraft_version = versions["minecraft"]
    found = {}
    target = cache / f"minecraft-{minecraft_version}.jar"
    if not target.is_file():
        manifest = json.loads(_get("https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"))
        url = next(v["url"] for v in manifest["versions"] if v["id"] == minecraft_version)
        target.write_bytes(_get(json.loads(_get(url))["downloads"]["client"]["url"]))
    found["minecraft"] = target
    for jar_id in ("sodium", "distanthorizons"):
        version = versions[jar_id]
        target = cache / f"{jar_id}-{version}-{minecraft_version}.jar"
        if not target.is_file():
            entry = next((v for v in _modrinth_versions(MODRINTH[jar_id], minecraft_version) if _is_version(v, version)), None)
            if entry is None:
                raise RuntimeError(f"Modrinth has no {NAMES[jar_id]} {version} for Minecraft {minecraft_version}")
            primary = next(f for f in entry["files"] if f["primary"])
            target.write_bytes(_get(primary["url"]))
        found[jar_id] = target
    return found


class Sources:
    """Shaders by namespace and path, from the pack first, then the jars."""

    def __init__(self, pack_path, jars: dict):
        self.assets = Path(pack_path) / "assets"
        self.jars = {jar_id: zipfile.ZipFile(path) for jar_id, path in jars.items()}

    def original(self, namespace: str, path: str):
        """The shader as the game or a mod has it, or None."""
        for z in self.jars.values():
            try:
                return z.read(f"assets/{namespace}/shaders/{path}").decode("utf-8", "replace")
            except KeyError:
                pass
        return None

    def read(self, namespace: str, path: str):
        """(text, where from), or (None, None) where nothing has it."""
        local = self.assets / namespace / "shaders" / path
        if local.is_file():
            return local.read_text(encoding="utf-8-sig", errors="replace"), "pack"
        text = self.original(namespace, path)
        return (text, "jar") if text is not None else (None, None)

    def exists(self, namespace: str, path: str) -> bool:
        return self.read(namespace, path)[0] is not None

    def listing(self, namespace: str, folder: str) -> set:
        """The file names in a shaders/ folder, the pack's and the jars'."""
        names = set()
        local = self.assets / namespace / "shaders" / folder
        if local.is_dir():
            names.update(p.name for p in local.iterdir() if p.is_file())
        prefix = f"assets/{namespace}/shaders/{folder}/"
        for z in self.jars.values():
            names.update(n[len(prefix):] for n in z.namelist() if n.startswith(prefix) and "/" not in n[len(prefix):] and n != prefix)
        return names

    def expand(self, namespace: str, path: str, defines=()) -> str:
        """The shader as the driver gets it: its imports filled in, as the
        game's preprocessor does, and the defines after its #version."""
        text, _ = self.read(namespace, path)
        body = self._imports(text, namespace, path, [])
        lines = body.split("\n")
        at = next((i for i, line in enumerate(lines) if VERSION.match(line)), -1)
        lines[at + 1:at + 1] = [f"#define {d}" for d in defines] + [f"#line {at + 2}"]
        return "\n".join(lines)

    def _imports(self, text: str, namespace: str, path: str, stack: list) -> str:
        def fill(match):
            relative, identifier = match.groups()
            if relative is not None:
                ns, target = namespace, str(Path(path).parent / relative).replace("\\", "/")
            else:
                ns, _, name = identifier.strip().rpartition(":")
                ns, target = ns or "minecraft", "include/" + name
            if (ns, target) in stack:
                return ""
            included, _ = self.read(ns, target)
            if included is None:
                raise FileNotFoundError(f"{ns}:{target}")
            included = VERSION.sub("", included)
            return self._imports(included, ns, target, stack + [(ns, target)])

        return MOJ_IMPORT.sub(fill, text)


# --- rules ---------------------------------------------------------------------

def pack_shaders(pack_path):
    """(namespace, path in shaders/, file) for every shader file the pack has."""
    assets = Path(pack_path) / "assets"
    for shader in sorted(assets.glob("*/shaders/**/*")):
        if shader.is_file() and shader.suffix in SHADER_SUFFIXES:
            namespace = shader.relative_to(assets).parts[0]
            yield namespace, shader.relative_to(assets / namespace / "shaders").as_posix(), shader


def check_rules(pack_path) -> list:
    """Every #version above MAX_VERSION, every ES shader and every #extension
    not allowed, in every shader file the pack has."""
    problems = []
    for namespace, path, shader in pack_shaders(pack_path):
        text = strip_comments(shader.read_text(encoding="utf-8-sig", errors="replace"))
        where = f"{namespace}:{path}"
        for match in VERSION.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            number, profile = int(match.group(1)), (match.group(2) or "").strip()
            if number > MAX_VERSION:
                problems.append(f"{where}:{line}: #version {number} - macOS stops at {MAX_VERSION}")
            if profile == "es":
                problems.append(f"{where}:{line}: #version {number} es - desktop OpenGL doesn't take ES shaders")
        for match in EXTENSION.finditer(text):
            if match.group(1) not in ALLOWED_EXTENSIONS:
                line = text.count("\n", 0, match.start()) + 1
                problems.append(f"{where}:{line}: #extension {match.group(1)} - not on every platform")
        if shader.suffix in STAGES and not VERSION.search(text):
            problems.append(f"{where}: no #version - drivers each guess a different one")
    return problems


# --- Distant Horizons' originals ----------------------------------------------

DECLARATION = re.compile(
    r"^[ \t]*(?:layout\s*\([^)]*\)\s*)?(?:(?:flat|smooth|noperspective|centroid|highp|mediump|lowp)\s+)*"
    r"(uniform|in|out|attribute|varying)\s+(\w+)\s+(\w+)\s*(?:\[[^\]]*\])?\s*(?:=[^;]*)?;", re.M)
BLOCK = re.compile(r"^[ \t]*(?:layout\s*\([^)]*\)\s*)?uniform\s+(\w+)\s*\{([^}]*)\}", re.M)
MEMBER = re.compile(r"(\w+)\s+(\w+)\s*(?:\[[^\]]*\])?\s*;")


def interface(text: str) -> dict:
    """What a shader takes and gives: (in/out/uniform, name) -> type, a uniform
    block's members as block.member."""
    text = strip_comments(text)
    found = {}
    for block, members in BLOCK.findall(text):
        for kind, name in MEMBER.findall(members):
            found[("uniform", f"{block}.{name}")] = kind
    for qualifier, kind, name in DECLARATION.findall(text):
        qualifier = {"attribute": "in", "varying": "out"}.get(qualifier, qualifier)
        found[(qualifier, name)] = kind
    return found


def check_dh_overrides(pack_path, sources: Sources) -> list:
    """Each of the pack's DH shaders against DH's own of that name: one DH no
    longer has, or an input, output or uniform DH's has that the pack's lacks
    or has as another type."""
    if "distanthorizons" not in sources.jars:
        return []
    problems = []
    for namespace, path, shader in pack_shaders(pack_path):
        if namespace != "distanthorizons" or shader.suffix not in STAGES:
            continue
        original = sources.original(namespace, path)
        where = f"{namespace}:{path}"
        if original is None:
            problems.append(f"{where}: Distant Horizons has no such shader any more - the override is never used")
            continue
        ours = interface(shader.read_text(encoding="utf-8-sig", errors="replace"))
        for key, kind in interface(original).items():
            if key not in ours:
                problems.append(f"{where}: Distant Horizons' has `{key[0]} {kind} {key[1]}`, which the override lacks - DH changed it since")
            elif ours[key] != kind:
                problems.append(f"{where}: Distant Horizons' `{key[0]} {key[1]}` is {kind}, the override's {ours[key]} - DH changed it since")
    return problems


# --- compiling -----------------------------------------------------------------

def programs(pack_path, sources: Sources) -> list:
    """(namespace, vertex path, fragment path) of every program a shader of the
    pack runs in, each stage the pack's or the original; None where a stage
    has no partner to be found."""
    found = []
    for namespace, path, shader in pack_shaders(pack_path):
        stage = STAGES.get(shader.suffix)
        if stage is None or "/include/" in f"/{path}":
            continue
        folder, stem = str(Path(path).parent).replace("\\", "/"), Path(path).stem
        names = sources.listing(namespace, folder)
        if namespace == "distanthorizons":
            if stage == "frag":
                vertex = next((n for n in ("vert.vsh", "vert.vert") if n in names), None)
                vertex = f"{folder}/{vertex}" if vertex else (DH_SHARED_VERTEX if folder.endswith("/gl") else None)
                pairs = [(vertex, path)]
            else:
                pairs = [(path, f"{folder}/{n}") for n in sorted(names) if Path(n).suffix in (".fsh", ".frag")] or [(path, None)]
        else:
            other = {"vert": (".fsh", ".frag"), "frag": (".vsh", ".vert")}[stage]
            partner = next((f"{folder}/{stem}{s}" for s in other if f"{stem}{s}" in names), None)
            if partner is None and stage == "frag" and (namespace, folder) == ("minecraft", "core"):
                partner = MINECRAFT_SHARED_VERTEX
            pairs = [(path, partner) if stage == "vert" else (partner, path)]
        for vertex, fragment in pairs:
            if vertex is not None and not sources.exists(namespace, vertex):
                vertex = None
            if fragment is not None and not sources.exists(namespace, fragment):
                fragment = None
            program = (namespace, vertex, fragment)
            if program not in found:
                found.append(program)
    return found


def find_glslang(given=None):
    for candidate in (given, os.environ.get("GLSLANG"), shutil.which("glslang"), shutil.which("glslangValidator")):
        if candidate and Path(candidate).is_file():
            return candidate
    return None


def driver_context():
    """A headless OpenGL context to compile on, or None without moderngl."""
    try:
        import moderngl
    except ImportError:
        return None
    backend = os.environ.get("MCME_GL_BACKEND")
    try:
        return moderngl.create_standalone_context(require=330, **({"backend": backend} if backend else {}))
    except Exception as e:  # no display, no driver
        print(f"No OpenGL context to link on: {e}")
        return None


def _glslang(glslang: str, text: str, stage: str):
    """glslang's complaint, or None if it compiles."""
    with tempfile.TemporaryDirectory() as folder:
        source = Path(folder) / f"shader.{stage}"
        source.write_text(text, encoding="utf-8")
        result = subprocess.run([glslang, "-S", stage, str(source)], capture_output=True, text=True)
    if result.returncode == 0:
        return None
    lines = [line for line in (result.stdout + result.stderr).splitlines()
             if line.strip() and not line.startswith(str(source)) and "compilation terminated" not in line]
    return "\n      ".join(lines[:12])


def compile_pack(pack_path, sources: Sources, glslang=None, context=None) -> Report:
    report = Report()
    seen = {}
    for namespace, vertex, fragment in programs(pack_path, sources):
        key = (vertex or fragment).rsplit(".", 1)[0]
        variants = DEFINES.get((namespace, key)) or DEFINES.get((namespace, (fragment or vertex).rsplit(".", 1)[0])) or [[]]
        for defines in variants:
            label = f"{namespace}:{vertex or '-'} + {fragment or '-'}" + (f" [{', '.join(defines)}]" if defines else "")
            texts = {}
            failed = False
            for stage, path in (("vert", vertex), ("frag", fragment)):
                if path is None:
                    continue
                try:
                    texts[stage] = sources.expand(namespace, path, defines)
                except FileNotFoundError as e:
                    report.problems.append(f"{namespace}:{path}: imports {e}, which nothing has")
                    failed = True
                    continue
                if glslang and (namespace, path, tuple(defines)) not in seen:
                    error = _glslang(glslang, texts[stage], stage)
                    seen[(namespace, path, tuple(defines))] = error
                    if error:
                        report.problems.append(f"{namespace}:{path}" + (f" [{', '.join(defines)}]" if defines else "")
                                               + f" doesn't compile (glslang):\n      {error}")
                        failed = True
                elif seen.get((namespace, path, tuple(defines))):
                    failed = True
            if context is not None and not failed and len(texts) == 2:
                try:
                    context.program(vertex_shader=texts["vert"], fragment_shader=texts["frag"]).release()
                except Exception as e:
                    message = "\n      ".join(str(e).strip().splitlines()[:12])
                    report.problems.append(f"{label} doesn't link on {context.info['GL_RENDERER']}:\n      {message}")
                    failed = True
            if not failed:
                report.notes.append(f"OK {label}")
    return report


def check(pack_path, jars: dict, glslang=None, context=None) -> Report:
    """Every check there is the means for: rules always, Distant Horizons'
    originals with DH's jar, compiling with glslang or a driver context."""
    sources = Sources(pack_path, jars)
    report = Report(problems=check_rules(pack_path))
    report.problems += check_dh_overrides(pack_path, sources)
    if glslang or context:
        compiled = compile_pack(pack_path, sources, glslang, context)
        report.problems += compiled.problems
        report.notes += compiled.notes
    return report


def tested_versions() -> dict:
    return json.loads(VERSIONS_PATH.read_text(encoding="utf-8"))
