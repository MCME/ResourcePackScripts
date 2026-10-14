"""The Bedrock pack's own files: manifest.json and pack_icon.png.

Bedrock knows a pack by its UUID and caches it by UUID and version. The UUIDs
are worked out from the pack's name, so every release of a pack has the same
ones and replaces the last, and the version from the release tag: v4.1.3 is
[4, 1, 3]. A client that has a version already doesn't download it again, so
reusing a tag (which the RP server allows) leaves Bedrock players with the
pack they had.
"""

import json
import re
import shutil
import uuid
import zipfile
from pathlib import Path

# Any fixed UUID: changing it gives every pack new UUIDs, as if it were a new pack
NAMESPACE = uuid.UUID("5c3f6a2e-8d1b-4f7a-9e2c-6b0d4a1f3e57")
# The oldest Bedrock that reads everything this pack uses: block geometry with
# material instances in one component, and tint methods
MIN_ENGINE_VERSION = [1, 21, 80]


def version_from_tag(tag: str | None) -> list[int]:
    """The first three numbers of a tag: v4.1.3 -> [4, 1, 3], v2 -> [2, 0, 0]."""
    numbers = [int(n) for n in re.findall(r"\d+", tag or "")][:3]
    while len(numbers) < 3:
        numbers.append(0)
    if numbers == [0, 0, 0]:
        numbers = [0, 0, 1]
    return numbers


def pack_uuids(key: str) -> tuple[str, str]:
    """(header UUID, resources module UUID) for a pack."""
    return str(uuid.uuid5(NAMESPACE, f"{key}/header")), str(uuid.uuid5(NAMESPACE, f"{key}/resources"))


def java_description(pack: Path) -> str:
    """The Java pack.mcmeta's description as plain text, or "" when there's none."""
    try:
        with open(Path(pack) / "pack.mcmeta", encoding="utf-8-sig") as f:
            description = json.load(f)["pack"]["description"]
    except (OSError, ValueError, KeyError, TypeError):
        return ""
    return _plain(description)


def _plain(component) -> str:
    if isinstance(component, str):
        return component
    if isinstance(component, list):
        return "".join(_plain(c) for c in component)
    if isinstance(component, dict):
        return _plain(component.get("text", "")) + _plain(component.get("extra", []))
    return ""


def write_manifest(root: Path, key: str, name: str, description: str, version: list[int]):
    header, module = pack_uuids(key)
    manifest = {
        "format_version": 2,
        "header": {
            "name": name,
            "description": description,
            "uuid": header,
            "version": version,
            "min_engine_version": MIN_ENGINE_VERSION,
        },
        "modules": [
            {"type": "resources", "uuid": module, "version": version, "description": description},
        ],
        "metadata": {"generated_with": {"mcme_generateBedrock": ["1.0.0"]}},
    }
    root.mkdir(parents=True, exist_ok=True)
    with open(root / "manifest.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")


def copy_icon(pack: Path, root: Path):
    icon = Path(pack) / "pack.png"
    if icon.is_file() and not icon.is_symlink():
        shutil.copyfile(icon, root / "pack_icon.png")


def zip_pack(root: Path, target: Path):
    """The pack as a .mcpack: a zip with manifest.json at its top."""
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(Path(root).rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(root).as_posix())
