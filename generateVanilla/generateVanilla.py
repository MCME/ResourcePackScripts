import shutil

import yaml
import json
import subprocess
import os
import argparse
from pathlib import Path
from PIL import Image

import constants
import processBlockstate
import util
import processItem
import hardcodedFiles

parser = argparse.ArgumentParser(description='Convert OBJ models to vanilla shader models.')

# add command line arguments
parser.add_argument('input_path', help='Path to read OBJ models from')
parser.add_argument('output_path', help='Path to write vanilla shader models in.')
parser.add_argument('vanilla_path', help='Path to read vanilla RP from.')
parser.add_argument('--limit',
                    help='Limit for number of alternate models for one blockstate. Defaults to no limit.',
                    default="-1")
parser.add_argument('--objmc',
                    help='Path to objmc script. Defaults to working directory.',
                    default='objmc.py')
parser.add_argument('--debug', action='store_true', help='Create debug output.')
parser.add_argument('--compress', action='store_true', help='Compress generated .json files.')
parser.add_argument('--noblocks', action='store_true', help='Do not process blockstate files.')
parser.add_argument('--noitems', action='store_true', help='Do not process item models files.')

# parse arguments
args = parser.parse_args()

print(f'Source path: {args.input_path}')
print(f'Output path: {args.output_path}')
print(f'Vanilla path: {args.vanilla_path}')

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

pack_mcmeta_file = input_path / constants.PACK_MCMETA
if pack_mcmeta_file.exists():
    with open(pack_mcmeta_file, 'r') as f:
        data = json.load(f)
        data['pack']['description'] = data['pack']['description'].replace("Sodium", "Vanilla")
    pack_mcmeta_file = output_path / constants.PACK_MCMETA
    if not pack_mcmeta_file.exists():
        pack_mcmeta_file.touch(exist_ok=True)
    with open(pack_mcmeta_file, 'w') as f:
        json.dump(data, f, indent=4)  # type: ignore
if (input_path / constants.PACK_PNG).exists():
    shutil.copy(input_path / constants.PACK_PNG, output_path / constants.PACK_PNG)
if (input_path / constants.LICENCE).exists():
    shutil.copy(input_path / constants.LICENCE, output_path / constants.LICENCE)
if (input_path / constants.README).exists():
    shutil.copy(input_path / constants.README, output_path / constants.README)

util.copy_folder(input_path / constants.RELATIVE_VANILLA_OVERRIDES_PATH / constants.RELATIVE_SHADER_PATH,
                 output_path / constants.RELATIVE_SHADER_PATH)
util.copy_folder(input_path / constants.RELATIVE_OPTIFINE_PATH, output_path / constants.RELATIVE_OPTIFINE_PATH)
util.copy_folder(input_path / constants.RELATIVE_TEXTS_PATH, output_path / constants.RELATIVE_TEXTS_PATH)
util.copy_folder(input_path / constants.RELATIVE_TEXTURES_ENV_PATH,
                 output_path / constants.RELATIVE_TEXTURES_ENV_PATH)
util.copy_folder(input_path / constants.RELATIVE_TEXTURES_GUI_PATH,
                 output_path / constants.RELATIVE_TEXTURES_GUI_PATH)
util.copy_folder(input_path / constants.RELATIVE_TEXTURES_ENTITY_PATH,
                 output_path / constants.RELATIVE_TEXTURES_ENTITY_PATH)
util.copy_folder(input_path / constants.RELATIVE_TEXTURES_COLORMAP_PATH,
                 output_path / constants.RELATIVE_TEXTURES_COLORMAP_PATH)
util.copy_folder(input_path / constants.RELATIVE_TEXTURES_PARTICLE_PATH,
                 output_path / constants.RELATIVE_TEXTURES_PARTICLE_PATH)
util.copy_folder(input_path / constants.RELATIVE_TEXTURES_PAINTING_PATH,
                 output_path / constants.RELATIVE_TEXTURES_PAINTING_PATH)
util.copy_folder(input_path / constants.RELATIVE_TEXTURES_ARMOR_PATH,
                 output_path / constants.RELATIVE_TEXTURES_ARMOR_PATH)
util.copy_folder(input_path / constants.RELATIVE_SOUNDS_PATH / Path("sounds"),
                 output_path / constants.RELATIVE_SOUNDS_PATH / Path("sounds"))
sound_json = constants.RELATIVE_SOUNDS_PATH / Path("sounds.json")
if (input_path / sound_json).exists():
    shutil.copy(input_path / sound_json, output_path / sound_json)

for folder in input_path.iterdir():
    if folder.is_dir() and folder.name.startswith("1_"):
        util.copy_folder(folder, output_path / Path(folder.name))
for folder in (input_path / constants.RELATIVE_VANILLA_OVERRIDES_PATH).iterdir():
    if folder.is_dir() and folder.name.startswith("1_"):
        util.copy_folder(folder, output_path / Path(folder.name))
if not no_blocks:
    for blockstate_file in (vanilla_path / constants.RELATIVE_BLOCKSTATE_PATH)\
                        .glob("*"+constants.BLOCKSTATE_EXTENSION):
        if blockstate_file.is_file():
            processBlockstate.process(input_path, output_path, vanilla_path, blockstate_file.name,
                                      limit, compress, objmc_path, debug)
if not no_items:
    for item_file in (vanilla_path / constants.RELATIVE_ITEMS_PATH).glob("*"+constants.ITEM_EXTENSION):
        if item_file.is_file():
            processItem.process(input_path, output_path, vanilla_path, item_file.name, compress, debug)
for model in hardcodedFiles.MODELS:
    file = input_path / constants.RELATIVE_VANILLA_MODELS_PATH / Path(model + constants.VANILLA_MODEL_EXTENSION)
    if file.exists():
        shutil.copy(file,
                    output_path / constants.RELATIVE_VANILLA_MODELS_PATH
                                / Path(model + constants.VANILLA_MODEL_EXTENSION))
for model in hardcodedFiles.TEXTURES:
    file = input_path / constants.RELATIVE_VANILLA_TEXTURES_PATH / Path(model + constants.TEXTURE_EXTENSION)
    meta_file = (input_path / constants.RELATIVE_VANILLA_TEXTURES_PATH
                            / Path(model + constants.TEXTURE_EXTENSION + constants.MCMETA_EXTENSION))
    print(meta_file)
    if file.exists():
        shutil.copy(file,
                    output_path / constants.RELATIVE_VANILLA_TEXTURES_PATH
                                / Path(model + constants.TEXTURE_EXTENSION))
    if meta_file.exists():
        shutil.copy(meta_file,
                    output_path / constants.RELATIVE_VANILLA_TEXTURES_PATH
                                / Path(model + constants.TEXTURE_EXTENSION + constants.MCMETA_EXTENSION))
