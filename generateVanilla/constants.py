from pathlib import Path

RELATIVE_VANILLA_OVERRIDES_PATH = Path("vanilla")

RELATIVE_ITEMS_PATH = Path("assets/minecraft/items")
RELATIVE_VANILLA_MODELS_PATH = Path("assets/minecraft/models")
RELATIVE_BLOCKSTATE_PATH = Path("assets/minecraft/blockstates")
RELATIVE_VANILLA_TEXTURES_PATH = Path("assets/minecraft/textures")

RELATIVE_SODIUM_MODELS_PATH = Path("assets/mcme/models")
RELATIVE_SODIUM_TEXTURES_PATH = Path("assets/mcme/textures")

# * blockstates
# * items
# * models
#   * block and item
# * textures
#  * block and item

# Relative suffixes (after assets/<namespace>/) to skip during copytree.
# These are processed separately by the blockstate/item/model pipeline
# These blockstates/items/models/textures will only exist in the generated vanilla pack if a vanilla block or item exists in the RP
IGNORED_ASSET_SUFFIXES = {
    Path("blockstates"),
    Path("items"),
    Path("models"),
    # Unable to ignore the entire textures folder because textures can be used for things like fonts
    Path("textures/block"),
    Path("textures/item"),
}

# Full paths (assets/<namespace>/...) to skip — for namespace-specific dirs
IGNORED_ASSET_PATHS = {
    Path("assets/mcme/sml_load_scopes"),
}

OBJ_MODEL_EXTENSION = ".obj"
VANILLA_MODEL_EXTENSION = ".json"
BLOCKSTATE_EXTENSION = ".json"
ITEM_EXTENSION = ".json"
TEXTURE_EXTENSION = ".png"
MCMETA_EXTENSION = ".mcmeta"
OBJMETA_EXTENSION = ".objmeta"
MTL_EXTENSION = ".mtl"

MCME_NAMESPACE = "mcme"
VANILLA_NAMESPACE = "minecraft"

PACK_MCMETA = "pack.mcmeta"
PACK_PNG = "pack.png"
LICENCE = "license.txt"
README = "README.md"

PARENT_DONE_VALUE = "PARENT DONE"
PARENT_SUFFIX = "_parent"
