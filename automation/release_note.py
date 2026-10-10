"""The note of a GitHub release: "Version <tag> for Minecraft <versions>".

The versions come from the zips themselves - each zip's pack.mcmeta declares
the pack formats it supports - translated through generateVanilla's
pack_formats.json. A note names only versions that every zip of the release
supports, and never guesses: formats the map doesn't know are left out, and a
range with no known format at all is named by its numbers.

    python3 release_note.py <tag> <zip> [<zip>...]
"""

import json
import sys
import zipfile
from pathlib import Path, PurePosixPath

FORMATS_PATH = Path(__file__).resolve().parent.parent / "generateVanilla" / "pack_formats.json"


class ReleaseNoteError(Exception):
    """A zip, or a pack.mcmeta, that no note can be worked out from."""


def _major(value):
    # Since Minecraft 1.21.9 a format may be written [major, minor]; versions
    # are told apart by the major part
    return value[0] if isinstance(value, list) and value else value


def _whole_number(value):
    return isinstance(value, int) and not isinstance(value, bool)


def format_range(pack):
    """(lowest, highest) pack format declared by a pack.mcmeta's "pack" section."""
    supported = pack.get("supported_formats")
    if "min_format" in pack and "max_format" in pack:
        lowest, highest = _major(pack["min_format"]), _major(pack["max_format"])
    elif isinstance(supported, list) and len(supported) == 2:
        lowest, highest = supported
    elif isinstance(supported, dict) and {"min_inclusive", "max_inclusive"} <= supported.keys():
        lowest, highest = supported["min_inclusive"], supported["max_inclusive"]
    elif supported is not None:
        lowest = highest = supported
    elif "pack_format" in pack:
        lowest = highest = pack["pack_format"]
    else:
        raise ReleaseNoteError("pack.mcmeta declares no pack format")
    if not (_whole_number(lowest) and _whole_number(highest)):
        raise ReleaseNoteError(f"pack format isn't a whole number: {lowest!r} to {highest!r}")
    if lowest > highest:
        # Minecraft refuses such a pack too; without this, note() would blame the other zips
        raise ReleaseNoteError(f"pack format range runs backwards: {lowest} to {highest}")
    return lowest, highest


def versions_in(lowest, highest, formats):
    """The Minecraft versions whose pack format lies in lowest..highest, oldest first."""
    return [formats[pack_format] for pack_format in sorted(formats) if lowest <= pack_format <= highest]


def _join(items):
    """'a', 'a and b', 'a, b and c'."""
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _span(lowest, highest):
    return str(lowest) if lowest == highest else f"{lowest}-{highest}"


def note(tag, ranges, formats):
    """(note text, warnings) for a release whose zips declare these format ranges."""
    distinct = sorted(set(ranges))
    listed = ", ".join(_span(low, high) for low, high in distinct)
    lowest = max(low for low, _ in distinct)
    highest = min(high for _, high in distinct)
    if lowest > highest:
        warning = f"no pack format is supported by every zip ({listed}), so the note names no Minecraft version"
        return f"Version {tag}", [warning]
    warnings = []
    # Ranges may differ harmlessly: a Sodium zip declares 15-255, the zips
    # converted from it 88-97. Warn only when the Minecraft versions differ.
    if len({tuple(versions_in(low, high, formats)) for low, high in distinct}) > 1:
        warnings.append(
            f"the zips support different Minecraft versions (pack formats {listed}); "
            "the note names only the versions they all support"
        )
    versions = versions_in(lowest, highest, formats)
    if versions:
        return f"Version {tag} for Minecraft {_join(versions)}", warnings
    return f"Version {tag} for pack format {_span(lowest, highest)}", warnings


def load_formats(path=FORMATS_PATH):
    """pack format -> Minecraft version, with the formats as numbers."""
    with open(path, encoding="utf-8") as f:
        return {int(pack_format): version for pack_format, version in json.load(f).items()}


def read_pack(zip_path):
    """The "pack" section of the zip's pack.mcmeta: the one at its root, else the shallowest."""
    try:
        with zipfile.ZipFile(zip_path) as archive:
            names = [n for n in archive.namelist() if PurePosixPath(n).name == "pack.mcmeta"]
            if not names:
                raise ReleaseNoteError(f"{zip_path}: no pack.mcmeta in the zip")
            name = min(names, key=lambda n: (n.count("/"), n))
            data = json.loads(archive.read(name).decode("utf-8-sig"))
    except (OSError, zipfile.BadZipFile, ValueError) as e:
        raise ReleaseNoteError(f"{zip_path}: {e}") from e
    pack = data.get("pack") if isinstance(data, dict) else None
    if not isinstance(pack, dict):
        raise ReleaseNoteError(f'{zip_path}: pack.mcmeta has no "pack" section')
    return pack


def zip_range(zip_path):
    """The pack format range a zip declares."""
    pack = read_pack(zip_path)
    try:
        return format_range(pack)
    except ReleaseNoteError as e:
        raise ReleaseNoteError(f"{zip_path}: {e}") from e


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if len(args) < 2:
        print("usage: release_note.py <tag> <zip> [<zip>...]", file=sys.stderr)
        return 2
    tag, zips = args[0], args[1:]
    try:
        text, warnings = note(tag, [zip_range(z) for z in zips], load_formats())
    except (ReleaseNoteError, OSError, ValueError) as e:
        print(f"release_note: {e}", file=sys.stderr)
        return 1
    for warning in warnings:
        print(f"release_note: warning: {warning}", file=sys.stderr)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
