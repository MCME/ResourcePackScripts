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


def copy_file(input_path, output_path, relative_file_path, required, debug, dest_file_path=None):
    """Copy a file from input to output. If dest_file_path is provided, use that as destination instead."""
    texture_override_file = input_path / constants.RELATIVE_VANILLA_OVERRIDES_PATH / relative_file_path
    texture_file = input_path / relative_file_path
    output_file = output_path / (dest_file_path if dest_file_path else relative_file_path)
    os.makedirs(output_file.parent, exist_ok=True)
    if texture_override_file.exists():
        util.printDebug(f"        Copying manual texture: {relative_file_path} to {output_file.relative_to(output_path) if dest_file_path else relative_file_path}", debug)
        os.makedirs(output_file.parent, exist_ok=True)
        shutil.copy(texture_override_file, output_file)
    elif texture_file.exists():
        util.printDebug(f"        Copying texture: {relative_file_path} to {output_file.relative_to(output_path) if dest_file_path else relative_file_path}", debug)
        os.makedirs(output_file.parent, exist_ok=True)
        if not output_file.exists():
            shutil.copy(texture_file, output_file)
    elif required:
        print(f"        WARNING! Texture file not found: {texture_file}")


def process_textures(input_path, output_path, textures, debug):
    for texture_name, texture_namespace_and_filename in textures.items():
        # Add default minecraft namespace if no namespace is present
        if ":" not in texture_namespace_and_filename:
            texture_namespace_and_filename = "minecraft:" + texture_namespace_and_filename
        
        util.printDebug("    Process item texture: "+texture_namespace_and_filename, debug)
        relative_path = util.get_relative_texture_path(texture_namespace_and_filename)
        texture_filename = texture_namespace_and_filename.split(":")[-1]
        
        # Determine source and destination paths
        # If this is an item/entity_ texture, the source is actually in entity/ folder
        if texture_filename.startswith("item/entity_"):
            # Source is in entity folder
            original_texture_filename = texture_filename.replace("item/entity_", "entity/", 1)
            source_file_relative = (relative_path / Path(original_texture_filename + constants.TEXTURE_EXTENSION))
            source_mcmeta_relative = (relative_path / Path(original_texture_filename + constants.TEXTURE_EXTENSION + constants.MCMETA_EXTENSION))
            
            # Destination is in item folder
            dest_file_relative = (relative_path / Path(texture_filename + constants.TEXTURE_EXTENSION))
            dest_mcmeta_relative = (relative_path / Path(texture_filename + constants.TEXTURE_EXTENSION + constants.MCMETA_EXTENSION))
            
            # Copy from entity to item location
            copy_file(input_path, output_path, source_file_relative, True, debug, dest_file_relative)
            copy_file(input_path, output_path, source_mcmeta_relative, False, debug, dest_mcmeta_relative)
        else:
            # Normal texture copy
            texture_file_relative = (relative_path / Path(texture_filename + constants.TEXTURE_EXTENSION))
            texture_mcmeta_file_relative = (relative_path / Path(texture_filename + constants.TEXTURE_EXTENSION + constants.MCMETA_EXTENSION))
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
    item_model = item_model.replace("mcme:", "")
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
        # Normalize texture paths to include namespace and convert entity textures to item paths
        for texture_key, texture_path in data["textures"].items():
            if ":" not in texture_path:
                texture_path = "minecraft:" + texture_path
            
            # Extract namespace and path
            namespace, path = texture_path.split(":", 1) if ":" in texture_path else ("minecraft", texture_path)
            
            # If texture is from entity folder, convert to item path for blocks atlas
            if path.startswith("entity/"):
                path = path.replace("entity/", "item/entity_", 1)
                texture_path = f"{namespace}:{path}"
                util.printDebug(f"        Converting entity texture to item path: {texture_path}", debug)
            
            data["textures"][texture_key] = texture_path
        
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


def is_composite(data):
    return data["type"] == "minecraft:composite" or data["type"] == "composite"


def process_model_entry(input_path, output_path, vanilla_path, model_entry, compress, debug):
    """
    Recursively process a model entry, handling both simple models and composite models.
    """
    if isinstance(model_entry, dict):
        # Check if this is a simple model reference
        if "type" in model_entry and is_model(model_entry):
            if "model" in model_entry:
                model_path = model_entry["model"]
                item_model = model_path + constants.VANILLA_MODEL_EXTENSION
                util.printDebug(f"    Processing model reference: {model_path}", debug)
                process_model(input_path, output_path, vanilla_path, get_relative_model_path(model_path),
                              item_model, compress, debug)
        
        # Check if this is a composite model with nested models
        elif "type" in model_entry and is_composite(model_entry):
            if "models" in model_entry:
                util.printDebug("    Processing composite model with nested models", debug)
                for nested_model in model_entry["models"]:
                    process_model_entry(input_path, output_path, vanilla_path, nested_model, compress, debug)
        
        # Also check for direct model reference without type
        elif "model" in model_entry and isinstance(model_entry["model"], str):
            model_path = model_entry["model"]
            item_model = model_path + constants.VANILLA_MODEL_EXTENSION
            util.printDebug(f"    Processing direct model reference: {model_path}", debug)
            process_model(input_path, output_path, vanilla_path, get_relative_model_path(model_path),
                          item_model, compress, debug)


def get_relative_model_path(namespaced_key):
    if "mcme:" in namespaced_key:
        return constants.RELATIVE_SODIUM_MODELS_PATH
    else:
        return constants.RELATIVE_VANILLA_MODELS_PATH


def process(input_path, output_path, vanilla_path, item_file_name, compress, debug):
    input_file = (input_path / constants.RELATIVE_VANILLA_OVERRIDES_PATH
                             / constants.RELATIVE_ITEMS_PATH / Path(item_file_name))
    if not input_file.exists():
        input_file = input_path / constants.RELATIVE_ITEMS_PATH / Path(item_file_name)
    is_vanilla_file = False
    if not input_file.exists():
        input_file = vanilla_path / constants.RELATIVE_ITEMS_PATH / Path(item_file_name)
        is_vanilla_file = True
    util.printDebug(f"Working on item file: {item_file_name}", debug)

    with open(input_file, 'r') as f:
        data = json.load(f)

    if "model" in data:
        # Check if the top-level model is itself a composite or simple model with a type
        if "type" in data["model"]:
            process_model_entry(input_path, output_path, vanilla_path, data["model"], compress, debug)
        # Otherwise check if it has a nested model
        elif "model" in data["model"]:
            process_model_entry(input_path, output_path, vanilla_path, data["model"], compress, debug)

        # Process fallback model if present
        if "fallback" in data["model"]:
            process_model_entry(input_path, output_path, vanilla_path, data["model"]["fallback"], compress, debug)

        # Process entries array (with threshold-based model selection)
        if "entries" in data["model"]:
            for entry in data["model"]["entries"]:
                if "model" in entry:
                    process_model_entry(input_path, output_path, vanilla_path, entry["model"], compress, debug)

    # write vanilla blockstate file
    if not is_vanilla_file:
        output_file = output_path / constants.RELATIVE_ITEMS_PATH / Path(item_file_name)
        os.makedirs(output_file.parent, exist_ok=True)
        with open(output_file, 'w') as file:
            if compress:
                json.dump(data, file, separators=(',', ':'))  # type: ignore
            else:
                json.dump(data, file, indent=4)  # type: ignore
