import shutil

import json
import os
import argparse
from pathlib import Path

import constants
import processBlockstate
import processItem
import hardcodedFiles

# ------------------------------------------------------------
# command line interface
# ------------------------------------------------------------
parser = argparse.ArgumentParser(
    description="Convert OBJ models to vanilla shader models."
)

# add command line arguments
parser.add_argument("input_path", help="Path to read OBJ models from")
parser.add_argument("output_path", help="Path to write vanilla shader models in.")
parser.add_argument("vanilla_path", help="Path to read vanilla RP from.")
parser.add_argument(
    "--limit",
    help="Limit for number of alternate models for one blockstate. Defaults to no limit.",
    default="-1",
)
parser.add_argument(
    "--objmc",
    help="Path to objmc script. Defaults to working directory.",
    default="objmc.py",
)
parser.add_argument("--debug", action="store_true", help="Create debug output.")
parser.add_argument(
    "--compress", action="store_true", help="Compress generated .json files."
)
parser.add_argument(
    "--noblocks", action="store_true", help="Do not process blockstate files."
)
parser.add_argument(
    "--noitems", action="store_true", help="Do not process item models files."
)

# parse arguments
args = parser.parse_args()

print(f"Source path: {args.input_path}")
print(f"Output path: {args.output_path}")
print(f"Vanilla path: {args.vanilla_path}")

# resolve paths and runtime flags

vanilla_path = Path(args.vanilla_path)
input_path = Path(args.input_path)
output_path = Path(args.output_path)
objmc_path = Path(args.objmc)
debug = args.debug
limit = int(args.limit)
compress = args.compress
no_blocks = args.noblocks
no_items = args.noitems

print("Generating vanilla resource pack!")

if not output_path.exists():
    os.makedirs(output_path)

print(f"Processing Sodium RP in: {input_path}")

# ----------------------------------------
# Bring over top level files
# ----------------------------------------
input_pack_mcmeta = input_path / constants.PACK_MCMETA
if input_pack_mcmeta.exists():
    with open(input_pack_mcmeta, "r") as f:
        data = json.load(f)
        data["pack"]["description"] = data["pack"]["description"].replace(
            "Sodium", "Vanilla"
        )
    output_pack_mcmeta = output_path / constants.PACK_MCMETA
    with open(output_pack_mcmeta, "w") as f:
        json.dump(data, f, indent=4)  # type: ignore

root_files = [constants.PACK_PNG, constants.LICENCE, constants.README]
for filename in root_files:
    src_path = input_path / filename
    if src_path.exists():
        shutil.copy(src_path, output_path / filename)


# ----------------------------------------
# Copy assets
# ----------------------------------------
def ignore_sodium_dirs(directory, contents):
    # Directory is the directory currently being copied
    # We strip input_path from it to just get "assets/..."
    rel = Path(directory).relative_to(input_path)
    # Return the entries of contents that are in SODIUM_DIRS
    return [name for name in contents if (rel / name) in constants.SODIUM_DIRS]


shutil.copytree(
    input_path / "assets",
    output_path / "assets",
    ignore=ignore_sodium_dirs,  # skip sodium-specific dirs that need conversion
    dirs_exist_ok=True,
)

# apply vanilla overrides on top (these take priority over main assets)
vanilla_assets = input_path / constants.RELATIVE_VANILLA_OVERRIDES_PATH / "assets"
if vanilla_assets.exists():
    shutil.copytree(vanilla_assets, output_path / "assets", dirs_exist_ok=True)

# copy version-specific folders from vanilla overrides (e.g., 1_21_1)
for folder in input_path.iterdir():
    if folder.is_dir() and folder.name.startswith("1_"):
        shutil.copytree(folder, output_path / folder.name, dirs_exist_ok=True)
for folder in (input_path / constants.RELATIVE_VANILLA_OVERRIDES_PATH).iterdir():
    if folder.is_dir() and folder.name.startswith("1_"):
        shutil.copytree(folder, output_path / folder.name, dirs_exist_ok=True)

# ---------------------------------------------
# Process vanilla blockstates and item models
# ---------------------------------------------
if not no_blocks:
    for blockstate_file in (vanilla_path / constants.RELATIVE_BLOCKSTATE_PATH).glob(
        "*" + constants.BLOCKSTATE_EXTENSION
    ):
        if blockstate_file.is_file():
            processBlockstate.process(
                input_path,
                output_path,
                vanilla_path,
                blockstate_file.name,
                limit,
                compress,
                objmc_path,
                debug,
            )

if not no_items:
    for item_file in (vanilla_path / constants.RELATIVE_ITEMS_PATH).glob(
        "*" + constants.ITEM_EXTENSION
    ):
        if item_file.is_file():
            processItem.process(
                input_path, output_path, vanilla_path, item_file.name, compress, debug
            )

for model in hardcodedFiles.MODELS:
    file = (
        input_path
        / constants.RELATIVE_VANILLA_MODELS_PATH
        / Path(model + constants.VANILLA_MODEL_EXTENSION)
    )
    if file.exists():
        shutil.copy(
            file,
            output_path
            / constants.RELATIVE_VANILLA_MODELS_PATH
            / Path(model + constants.VANILLA_MODEL_EXTENSION),
        )
for model in hardcodedFiles.TEXTURES:
    file = (
        input_path
        / constants.RELATIVE_VANILLA_TEXTURES_PATH
        / Path(model + constants.TEXTURE_EXTENSION)
    )
    meta_file = (
        input_path
        / constants.RELATIVE_VANILLA_TEXTURES_PATH
        / Path(model + constants.TEXTURE_EXTENSION + constants.MCMETA_EXTENSION)
    )
    print(meta_file)
    if file.exists():
        shutil.copy(
            file,
            output_path
            / constants.RELATIVE_VANILLA_TEXTURES_PATH
            / Path(model + constants.TEXTURE_EXTENSION),
        )
    if meta_file.exists():
        shutil.copy(
            meta_file,
            output_path
            / constants.RELATIVE_VANILLA_TEXTURES_PATH
            / Path(model + constants.TEXTURE_EXTENSION + constants.MCMETA_EXTENSION),
        )
