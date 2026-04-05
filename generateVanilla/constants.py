from pathlib import Path

RELATIVE_VANILLA_OVERRIDES_PATH = Path("vanilla")

RELATIVE_ITEMS_PATH = Path("assets/minecraft/items")
RELATIVE_VANILLA_MODELS_PATH = Path("assets/minecraft/models")
RELATIVE_BLOCKSTATE_PATH = Path("assets/minecraft/blockstates")
RELATIVE_VANILLA_TEXTURES_PATH = Path("assets/minecraft/textures")

RELATIVE_SODIUM_MODELS_PATH = Path("assets/mcme/models")
RELATIVE_SODIUM_TEXTURES_PATH = Path("assets/mcme/textures")

SODIUM_DIRS = {
    Path("assets/minecraft/blockstates"),
    Path("assets/minecraft/items"),
    Path("assets/mcme/models/block"),
    Path("assets/mcme/textures/block"),
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
