"""The shader base every pack's shaders are built on.

The terrain, objmc and Sodium shaders that make objmc models show - with or
without Sodium - with the water they draw, and the shaders every pack shares
(the action bar's text.vsh, fog.glsl) live once, in this repository's
shaderBase/, and are added to each
pack as it's built. A pack adds features of its own through the base's hooks
(mcme_hook_*.glsl), never by shipping a base file of its own: two copies would
drift apart, which is how the packs came to break each other.

shaderBase/ is a resource pack too, so it can be loaded below a pack checkout
to work on that pack's shaders without building it. See docs/shader-base.md.
"""

import re
import shutil
from pathlib import Path

import fluid_signature

BASE_PATH = Path(__file__).resolve().parent.parent / "shaderBase"

HOOK_PATTERN = "mcme_hook_*.glsl"
HOOKS_PATH = Path("assets/minecraft/shaders/include")

# Shipped in every pack; the rest only in the packs whose terrain needs them
ALWAYS = {
    Path("assets/minecraft/shaders/core/text.vsh"),
    Path("assets/minecraft/shaders/include/fog.glsl"),
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

# As vanilla's GlslPreprocessor reads it: <namespace:path>, <path> (minecraft)
# or "path" (beside the importing file)
MOJ_IMPORT = re.compile(r'#\s*moj_import\s*(?:"([^"\n]*)"|<([^>\n]*)>)')


class ShaderBaseError(Exception):
    pass


def base_files() -> list[Path]:
    """Every file the base owns, relative to its folder - hooks included."""
    return sorted(
        p.relative_to(BASE_PATH)
        for p in (BASE_PATH / "assets").rglob("*")
        if p.is_file()
    )


def is_hook(relative: Path) -> bool:
    return relative.parent == HOOKS_PATH and relative.match(HOOK_PATTERN)


def needs_terrain(asset_roots) -> bool:
    """Whether a pack, given by the folders holding its assets/, needs the
    terrain shaders: it has objmc models to show, or features hooked in."""
    for root in asset_roots:
        assets = Path(root) / "assets"
        if not assets.is_dir():
            continue
        if next(assets.rglob("*.obj"), None) is not None:
            return True
        if next((Path(root) / HOOKS_PATH).glob(HOOK_PATTERN), None) is not None:
            return True
    return False


def conflicts(asset_roots) -> list[Path]:
    """The base's files a pack ships itself, other than hooks."""
    return [
        Path(root) / relative
        for root in asset_roots
        for relative in base_files()
        if not is_hook(relative) and (Path(root) / relative).is_file()
    ]


def apply(asset_roots, output_path):
    """Add the base to the pack built from `asset_roots` into `output_path`.

    `asset_roots` are the pack's folders holding an assets/ that end up in the
    output - its root, and for the vanilla pack its vanilla/ overrides. A hook
    the pack has is kept; the base's empty one is added otherwise.
    """
    found = conflicts(asset_roots)
    if found:
        raise ShaderBaseError(
            "The pack ships files the shader base owns (ResourcePackScripts/"
            "shaderBase). Delete them and hook pack features in through "
            "mcme_hook_*.glsl instead - see docs/shader-base.md:\n"
            + "\n".join(f"  {p}" for p in found)
        )
    terrain = needs_terrain(asset_roots)
    output_path = Path(output_path)
    for relative in base_files():
        if not terrain and relative not in ALWAYS:
            continue
        target = output_path / relative
        if is_hook(relative) and target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(BASE_PATH / relative, target)


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


def finish(pack_path):
    """Once the pack is complete: sign its water textures, if it has the base's
    water, and check that every shader import resolves."""
    pack_path = Path(pack_path)
    if (pack_path / HOOKS_PATH / "water.glsl").is_file():
        messages, ok = fluid_signature.sign_pack(pack_path, fluid_signature.WATER)
        if not ok:
            print(
                "WARNING!!! The water textures can't carry the codes the shaders "
                "know water by, so it shows plain:\n"
                + "\n".join(f"  {m}" for m in messages),
                flush=True,
            )
    check_imports(pack_path)


def check_imports(pack_path):
    missing = unresolved_imports(pack_path)
    if missing:
        raise ShaderBaseError(
            "Shader imports that don't resolve - the client would drop every "
            "resource pack on loading this one:\n"
            + "\n".join(f"  {m}" for m in missing)
        )
