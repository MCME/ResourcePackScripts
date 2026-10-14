"""Which faces Java tints, and how Bedrock is told to tint them the same way.

Java tints a face that names a `tintindex` only when the block has a colour
of its own (BlockColors.createDefault): grass and foliage by biome, a few
blocks by a fixed colour or by their state. The same face on any other block
keeps its texture's colours.

Bedrock tints a custom block's material by biome when the material names a
`tint_method` (since 1.21.80). Geyser builds a custom block's materials from
its `custom_mappings`, so the method has to be in the mappings - and
Geyser's mappings reader up to at least October 2026 doesn't read it yet,
so on such a Geyser biome-tinted faces show their grey texture. A pack can
set `"tint": "baked"` (bedrock_settings.py) to multiply a fixed colour into
the texture instead. Colours that don't depend on the biome are always baked.
"""

# Bedrock's tint methods for the biome colours Java uses
GRASS = "grass"
FOLIAGE = "default_foliage"
BIRCH = "birch_foliage"
EVERGREEN = "evergreen_foliage"
DRY_FOLIAGE = "dry_foliage"
WATER = "water"

# Plains, read from 26.2's colormaps (temperature 0.8, downfall 0.4); Java's
# birch and spruce leaves never vary by biome
DEFAULT_BAKED = {
    GRASS: "#91bd59",
    FOLIAGE: "#77ab2f",
    BIRCH: "#80a755",
    EVERGREEN: "#619961",
    DRY_FOLIAGE: "#a37546",
    WATER: "#3f76e4",
}

_BIOME_TINTED = {
    **dict.fromkeys(
        ["grass_block", "short_grass", "fern", "potted_fern", "bush", "tall_grass", "large_fern", "sugar_cane"], GRASS
    ),
    **dict.fromkeys(
        ["oak_leaves", "jungle_leaves", "acacia_leaves", "dark_oak_leaves", "vine", "mangrove_leaves"], FOLIAGE
    ),
    "birch_leaves": BIRCH,
    "spruce_leaves": EVERGREEN,
    "leaf_litter": DRY_FOLIAGE,
    **dict.fromkeys(["water", "bubble_column", "water_cauldron"], WATER),
}
# Tinted by biome grass on every tintindex but 0
_GRASS_BUT_FIRST = {"pink_petals", "wildflowers"}
_FIXED = {
    "lily_pad": 0x208030,
    "attached_melon_stem": 0xE0C71C,
    "attached_pumpkin_stem": 0xE0C71C,
}


def _redstone(power: int) -> int:
    """RedStoneWireBlock's colour for a power level."""
    f = power / 15.0
    r = f * 0.6 + (0.4 if f > 0 else 0.3)
    g = min(1.0, max(0.0, f * f * 0.7 - 0.5))
    b = min(1.0, max(0.0, f * f * 0.6 - 0.7))
    return (int(r * 255) << 16) | (int(g * 255) << 8) | int(b * 255)


def _stem(age: int) -> int:
    return ((age * 32) << 16) | ((255 - age * 8) << 8) | (age * 4)


def tint(block_path: str, state: dict[str, str], tintindex: int):
    """How Java tints a face: ("method", tint method), ("colour", 0xRRGGBB) or None."""
    if tintindex < 0:
        return None
    if block_path in _GRASS_BUT_FIRST:
        return ("method", GRASS) if tintindex != 0 else None
    if block_path in _BIOME_TINTED:
        return ("method", _BIOME_TINTED[block_path])
    if block_path in _FIXED:
        return ("colour", _FIXED[block_path])
    if block_path == "redstone_wire":
        return ("colour", _redstone(int(state.get("power", "0"))))
    if block_path in ("melon_stem", "pumpkin_stem"):
        return ("colour", _stem(int(state.get("age", "0"))))
    return None


def parse_colour(value) -> int:
    """'#77ab2f' -> 0x77ab2f."""
    text = str(value).strip().lstrip("#")
    if len(text) != 6:
        raise ValueError(f"not a #rrggbb colour: {value!r}")
    return int(text, 16)
