import shutil

from pathlib import Path

import util
import constants
import json
import os


def process_parent(input_path, output_path, parent, debug):
    util.printDebug("Process item parent: "+parent, debug)
    if not parent.startswith("builtin"):
        parent_file = (input_path / constants.RELATIVE_VANILLA_MODELS_PATH /
                                    (parent.split(":")[-1] + constants.VANILLA_MODEL_EXTENSION))
        if parent_file.exists():
            shutil.copy(parent_file, output_path / constants.RELATIVE_VANILLA_MODELS_PATH
                                                 / (parent + constants.VANILLA_MODEL_EXTENSION))


def process_textures(input_path, output_path, textures, debug):
    for texture_name, texture_filename in textures.items():
        util.printDebug("Process item texture: "+texture_filename, debug)
        texture_file_relative = (constants.RELATIVE_VANILLA_TEXTURES_PATH
                                 / Path(texture_filename.split(":")[-1] + constants.TEXTURE_EXTENSION))
        texture_file = input_path / texture_file_relative
        output_file = (output_path / texture_file_relative)
        os.makedirs(output_file.parent, exist_ok=True)
        if texture_file.exists():
            util.printDebug(f"        Copying texture: {texture_file_relative}", debug)
            shutil.copy(texture_file, output_file)


def process_overrides(input_path, output_path, vanilla_path, overrides, compress, debug):
    for part in overrides:
        util.printDebug("Process override: " + part, debug);
        process(input_path, output_path, vanilla_path, part["model"], compress, debug)


def process(input_path, output_path, vanilla_path, file, compress, debug):
    util.printDebug(f"Working on item model file: {file}", debug)
    input_file = input_path / constants.RELATIVE_ITEM_PATH / file
    is_vanilla_model = False
    if not input_file.exists():
        input_file = vanilla_path / constants.RELATIVE_ITEM_PATH / file
        is_vanilla_model = True

    with open(input_file, 'r') as f:
        data = json.load(f)

    # check blockstate structure
    if "parent" in data:
        process_parent(input_path, output_path, data["parent"], debug)
    if "textures" in data:
        process_textures(input_path, output_path, data["textures"], debug)
    if "override" in data:
        process_overrides(input_path, output_path, vanilla_path, data["overrides"], compress, debug)

    # write vanilla item model file
    if not is_vanilla_model:
        output_file = output_path / constants.RELATIVE_ITEM_PATH / file
        os.makedirs(output_file.parent, exist_ok=True)
        with open(output_file, 'w') as file:
            if compress:
                json.dump(data, file, separators=(',', ':'))
            else:
                json.dump(data, file, indent=4)
