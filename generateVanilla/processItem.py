import shutil

from pathlib import Path

import util
import constants
import json
import os


def process_parent(input_path, output_path, parent, debug):
    util.printDebug("Process item parent: "+parent, debug)
    if not parent.startswith("builtin"):
        parent = parent.split(":")[-1]
        parent_file = (input_path / constants.RELATIVE_VANILLA_MODELS_PATH /
                                    (parent + constants.VANILLA_MODEL_EXTENSION))
        if parent_file.exists():
            output_file = output_path / constants.RELATIVE_VANILLA_MODELS_PATH / (parent + constants.VANILLA_MODEL_EXTENSION)
            util.printDebug(f"        Copying model: {parent}", debug)
            # print("Input: "+str(parent_file))
            # print("Output: "+str(output_file))
            os.makedirs(output_file.parent, exist_ok=True)
            shutil.copy(parent_file, output_file)


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
            # print("Input: "+str(texture_file))
            # print("Output: "+str(output_file))
            os.makedirs(output_file.parent, exist_ok=True)
            shutil.copy(texture_file, output_file)


def process_overrides(input_path, output_path, vanilla_path, overrides, compress, debug):
    for part in overrides:
        util.printDebug("Process override: " + str(part), debug)
        process(input_path, output_path, vanilla_path,
                part["model"].split(":")[-1] + constants.VANILLA_MODEL_EXTENSION, compress, debug)


def process(input_path, output_path, vanilla_path, file, compress, debug):
    input_file = input_path / constants.RELATIVE_ITEM_PATH / file
    is_vanilla_model = False
    if not input_file.exists():
        input_file = vanilla_path / constants.RELATIVE_ITEM_PATH / file
        is_vanilla_model = True
    util.printDebug(f"Working on item model file: {file} Vanilla: {is_vanilla_model}", debug)

    with open(input_file, 'r') as f:
        data = json.load(f)

    # check blockstate structure
    if "parent" in data:
        process_parent(input_path, output_path, data["parent"], debug)
    if "textures" in data:
        process_textures(input_path, output_path, data["textures"], debug)
    if "overrides" in data:
        process_overrides(input_path, output_path, vanilla_path, data["overrides"], compress, debug)

    # write vanilla item model file
    if not is_vanilla_model:
        output_file = output_path / constants.RELATIVE_ITEM_PATH / file
        util.printDebug(f"Copying item model: {output_file}", debug)
        os.makedirs(output_file.parent, exist_ok=True)
        with open(output_file, 'w') as file:
            if compress:
                json.dump(data, file, separators=(',', ':'))
            else:
                json.dump(data, file, indent=4)
