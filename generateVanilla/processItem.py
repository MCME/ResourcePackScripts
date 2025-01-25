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


def copy_file(input_path, output_path, relative_file_path, required, debug):
    texture_override_file = input_path / constants.RELATIVE_VANILLA_OVERRIDES_PATH / relative_file_path
    texture_file = input_path / relative_file_path
    output_file = (output_path / relative_file_path)
    os.makedirs(output_file.parent, exist_ok=True)
    if texture_override_file.exists():
        util.printDebug(f"        Copying manual texture: {relative_file_path}", debug)
        os.makedirs(output_file.parent, exist_ok=True)
        shutil.copy(texture_override_file, output_file)
    elif texture_file.exists():
        util.printDebug(f"        Copying texture: {relative_file_path}", debug)
        os.makedirs(output_file.parent, exist_ok=True)
        if not output_file.exists():
            shutil.copy(texture_file, output_file)
    elif required:
        print(f"        WARNING! Texture file not found: {texture_file}")


def process_textures(input_path, output_path, textures, debug):
    for texture_name, texture_namespace_and_filename in textures.items():
        util.printDebug("    Process item texture: "+texture_namespace_and_filename, debug)
        relative_path = util.get_relative_texture_path(texture_namespace_and_filename)
        texture_filename = texture_namespace_and_filename.split(":")[-1]
        texture_file_relative = (relative_path / Path(texture_filename + constants.TEXTURE_EXTENSION))
        texture_mcmeta_file_relative = (relative_path / Path(texture_filename
                                        + constants.TEXTURE_EXTENSION + constants.MCMETA_EXTENSION))
        copy_file(input_path, output_path, texture_file_relative, True, debug)
        copy_file(input_path, output_path, texture_mcmeta_file_relative, False, debug)


def process_overrides(input_path, output_path, vanilla_path, item_model, overrides, compress, debug):
    for part in overrides:
        util.printDebug("    Process override: " + str(part), debug)
        relative_path = util.get_relative_model_path(part["model"])
        override_model = part["model"].split(":")[-1] + constants.VANILLA_MODEL_EXTENSION
        if not item_model == override_model:
            process_model(input_path, output_path, vanilla_path, relative_path, override_model, compress, debug)


def process_model(input_path, output_path, vanilla_path, relative_path, item_model, compress, debug):
    item_model = item_model.replace("minecraft:", "")
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
    util.printDebug(f"Working on item model file: {item_model} Vanilla: {is_vanilla_model} Manual: {is_manual_model}",
                    debug)
    if not input_file.exists():
        util.printDebug("    WARNING! Expected item model file not found: "
                        + str(input_path / relative_path / item_model), debug)
        return
    # print(input_file)
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


def is_model(data):
    return data["type"] == "minecraft:model" or data["type"] == "model"


def process(input_path, output_path, vanilla_path, item_file_name, compress, debug):
    input_file = input_path / constants.RELATIVE_ITEMS_PATH / Path(item_file_name)
    is_vanilla_file = False
    if not input_file.exists():
        input_file = vanilla_path / constants.RELATIVE_ITEMS_PATH / Path(item_file_name)
        is_vanilla_file = True
    util.printDebug(f"Working on item file: {item_file_name}", debug)

    with open(input_file, 'r') as f:
        data = json.load(f)

    if "model" in data:
        if "model" in data["model"]:
            if is_model(data["model"]):
                item_model = data["model"]["model"]+constants.VANILLA_MODEL_EXTENSION
                process_model(input_path, output_path, vanilla_path, constants.RELATIVE_VANILLA_MODELS_PATH,
                              item_model, compress, debug)

        if "fallback" in data["model"]:
            if is_model(data["model"]["fallback"]):
                item_model = data["model"]["fallback"]["model"]+constants.VANILLA_MODEL_EXTENSION
                print("fallback")
                process_model(input_path, output_path, vanilla_path, constants.RELATIVE_VANILLA_MODELS_PATH,
                              item_model, compress, debug)

        if "entries" in data["model"]:
            for entry in data["model"]["entries"]:
                if is_model(entry["model"]):
                    print("entry")
                    item_model = entry["model"]["model"]+constants.VANILLA_MODEL_EXTENSION
                    process_model(input_path, output_path, vanilla_path, constants.RELATIVE_VANILLA_MODELS_PATH,
                                  item_model, compress, debug)

    # write vanilla blockstate file
    if not is_vanilla_file:
        output_file = output_path / constants.RELATIVE_ITEMS_PATH / Path(item_file_name)
        os.makedirs(output_file.parent, exist_ok=True)
        with open(output_file, 'w') as file:
            if compress:
                json.dump(data, file, separators=(',', ':'))  # type: ignore
            else:
                json.dump(data, file, indent=4)  # type: ignore
