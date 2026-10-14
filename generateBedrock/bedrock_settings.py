"""A pack's Bedrock settings: the optional `.mcme-bedrock.json` at its top.

Like `.mcme-shaders.json`, the file starts with a dot, so the release scripts
never zip it. Every key is optional (docs/bedrock.md lists them):

    {
      "enabled": true,
      "name": "MCME Human",
      "geometry": "hybrid",
      "tint": "biome",
      "baked_colours": {"grass": "#91bd59"},
      "oversize": "keep",
      "reverse_polymesh_winding": false
    }

A value that can't be used is reported and its default kept: like the rest of
a pack, the file comes from many hands, and a typo in it mustn't stop a release.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

import geometry
import tints

FILE_NAME = ".mcme-bedrock.json"
TINTS = ("biome", "baked")
# The keys of "baked_colours", by the names docs/bedrock.md uses
_COLOUR_NAMES = {
    "grass": tints.GRASS,
    "foliage": tints.FOLIAGE,
    "birch_foliage": tints.BIRCH,
    "evergreen_foliage": tints.EVERGREEN,
    "dry_foliage": tints.DRY_FOLIAGE,
    "water": tints.WATER,
}


@dataclass
class Settings:
    enabled: bool = True
    name: str | None = None
    geometry: str = "hybrid"
    tint: str = "biome"
    baked_colours: dict[str, int] = field(
        default_factory=lambda: {k: tints.parse_colour(v) for k, v in tints.DEFAULT_BAKED.items()}
    )
    oversize: str = "keep"
    reverse_polymesh_winding: bool = False


def load(pack: Path, warn) -> Settings:
    settings = Settings()
    path = Path(pack) / FILE_NAME
    if not path.is_file():
        return settings
    try:
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        warn(f"Couldn't read {FILE_NAME} ({e}), so the Bedrock pack is made with the default settings")
        return settings
    if not isinstance(data, dict):
        warn(f"{FILE_NAME} isn't a JSON object, so the Bedrock pack is made with the default settings")
        return settings

    def choice(key, options):
        value = data.get(key)
        if value is None:
            return getattr(settings, key)
        if value not in options:
            warn(f"{FILE_NAME}: {key} is {value!r}, which isn't one of {', '.join(options)}; using {getattr(settings, key)!r}")
            return getattr(settings, key)
        return value

    def flag(key):
        value = data.get(key, getattr(settings, key))
        if not isinstance(value, bool):
            warn(f"{FILE_NAME}: {key} must be true or false, not {value!r}")
            return getattr(settings, key)
        return value

    settings.enabled = flag("enabled")
    settings.reverse_polymesh_winding = flag("reverse_polymesh_winding")
    settings.geometry = choice("geometry", geometry.MODES)
    settings.tint = choice("tint", TINTS)
    settings.oversize = choice("oversize", geometry.OVERSIZE)
    if isinstance(data.get("name"), str) and data["name"].strip():
        settings.name = data["name"].strip()
    for name, value in (data.get("baked_colours") or {}).items():
        if name not in _COLOUR_NAMES:
            warn(f"{FILE_NAME}: baked_colours has no colour called {name!r} (known: {', '.join(_COLOUR_NAMES)})")
            continue
        try:
            settings.baked_colours[_COLOUR_NAMES[name]] = tints.parse_colour(value)
        except ValueError as e:
            warn(f"{FILE_NAME}: baked_colours.{name}: {e}")
    unknown = set(data) - {"enabled", "name", "geometry", "tint", "baked_colours", "oversize", "reverse_polymesh_winding"}
    if unknown:
        warn(f"{FILE_NAME} has keys generateBedrock doesn't know: {', '.join(sorted(unknown))}")
    return settings
