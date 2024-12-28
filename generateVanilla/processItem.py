import shutil

from pathlib import Path

import util
import constants
import json
import os


def process_parent(input_path, output_path, parent, debug):
    util.printDebug("    Process item parent: "+parent, debug)
    if not parent.startswith("builtin"):
        relative_path = util.get_relative_model_path(parent)
        parent = parent.split(":")[-1]
        parent_file = (input_path / relative_path / (parent + constants.VANILLA_MODEL_EXTENSION))
        parent_override_file = (input_path / constants.RELATIVE_VANILLA_OVERRIDES_PATH /
                                relative_path / (parent + constants.VANILLA_MODEL_EXTENSION))
        output_file = (output_path / relative_path / (parent + constants.VANILLA_MODEL_EXTENSION))
        if parent_override_file.exists():
            util.printDebug(f"        Copying manual parent model: {parent}", debug)
            # print("Input: "+str(parent_file))
            # print("Output: "+str(output_file))
            os.makedirs(output_file.parent, exist_ok=True)
            shutil.copy(parent_override_file, output_file)
        elif parent_file.exists():
            util.printDebug(f"        Copying parent model: {parent}", debug)
            # print("Input: "+str(parent_file))
            # print("Output: "+str(output_file))
            if not output_file.exists():
                os.makedirs(output_file.parent, exist_ok=True)
                shutil.copy(parent_file, output_file)


def process_textures(input_path, output_path, textures, debug):
    for texture_name, texture_filename in textures.items():
        util.printDebug("    Process item texture: "+texture_filename, debug)
        relative_path = util.get_relative_texture_path(texture_filename)
        texture_file_relative = (relative_path / Path(texture_filename.split(":")[-1] + constants.TEXTURE_EXTENSION))
        texture_override_file = input_path / constants.RELATIVE_VANILLA_OVERRIDES_PATH / texture_file_relative
        texture_file = input_path / texture_file_relative
        output_file = (output_path / texture_file_relative)
        os.makedirs(output_file.parent, exist_ok=True)
        if texture_override_file.exists():
            util.printDebug(f"        Copying manual texture: {texture_file_relative}", debug)
            os.makedirs(output_file.parent, exist_ok=True)
            shutil.copy(texture_override_file, output_file)
        elif texture_file.exists():
            util.printDebug(f"        Copying texture: {texture_file_relative}", debug)
            # print("Input: "+str(texture_file))
            # print("Output: "+str(output_file))
            if not output_file.exists():
                os.makedirs(output_file.parent, exist_ok=True)
                shutil.copy(texture_file, output_file)


def process_overrides(input_path, output_path, vanilla_path, item_model, overrides, compress, debug):
    for part in overrides:
        util.printDebug("    Process override: " + str(part), debug)
        relative_path = util.get_relative_model_path(part["model"])
        override_model = part["model"].split(":")[-1] + constants.VANILLA_MODEL_EXTENSION
        if not item_model == override_model:
            process(input_path, output_path, vanilla_path, relative_path, override_model, compress, debug)


def process(input_path, output_path, vanilla_path, relative_path, item_model, compress, debug):
    is_vanilla_model = False
    is_manual_model = True
    input_file = input_path / constants.RELATIVE_VANILLA_OVERRIDES_PATH / relative_path / item_model
    # print(input_file)
    if not input_file.exists():
        input_file = input_path / relative_path / item_model
        is_manual_model = False
    if not input_file.exists():
        input_file = vanilla_path / relative_path / item_model
        is_vanilla_model = True
    util.printDebug(f"Working on item model file: {item_model} Vanilla: {is_vanilla_model} Manual: {is_manual_model}", debug)
    if not input_file.exists():
        util.printDebug("    WARNING! Expected item model file not found: "
                        + str(input_path / relative_path / item_model), debug)
        return
    with open(input_file, 'r') as f:
        data = json.load(f)

    # check blockstate structure
    if "parent" in data:
        process_parent(input_path, output_path, data["parent"], debug)
    if "textures" in data:
        process_textures(input_path, output_path, data["textures"], debug)
    if "overrides" in data:
        process_overrides(input_path, output_path, vanilla_path, item_model, data["overrides"], compress, debug)

    # write vanilla item model file
    if not is_vanilla_model:
        output_file = output_path / relative_path / item_model
        if not output_file.exists():
            util.printDebug(f"    Copying item model: {output_file}", debug)
            os.makedirs(output_file.parent, exist_ok=True)
            with open(output_file, 'w') as file:
                if compress:
                    json.dump(data, file, separators=(',', ':'))  # type: ignore
                else:
                    json.dump(data, file, indent=4)  # type: ignore
