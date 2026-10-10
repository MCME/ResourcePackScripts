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
