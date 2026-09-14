import json
import os
import shutil

import constants
import objmc_conversion
import util


# Copies one texture file, if the pack being read from actually has it.
def copy_texture_file(texture_path, output_path, texture_file_relative, debug):
    texture_file = texture_path / texture_file_relative
    if not texture_file.exists():
        return
    util.printDebug(f"        Copying texture: {texture_file_relative}", debug)
    os.makedirs((output_path / texture_file_relative).parent, exist_ok=True)
    shutil.copy(texture_file, output_path / texture_file_relative)


# Copies the textures a model names - but only if they exist in texture_path
def copy_textures(texture_path, output_path, model_data, debug):
    for texture_identifier in model_data.get("textures", {}).values():
        if texture_identifier.startswith("#"):
            # The texture is a variable reference, not a file to copy
            continue

        texture_file_relative = util.resolve_texture_file(texture_identifier)
        texture_mcmeta_file_relative = (
            texture_file_relative + constants.MCMETA_EXTENSION
        )
        copy_texture_file(texture_path, output_path, texture_file_relative, debug)
        copy_texture_file(
            texture_path, output_path, texture_mcmeta_file_relative, debug
        )


# Recursively walks a model chain, copying any models and textures that the input RP overrides
def copy_model_chain(
    input_path, output_path, vanilla_path, model_identifier: str, debug, visited=None
):
    model_file_relative = util.resolve_model_file(model_identifier)
    if model_file_relative is None:
        # A built-in model, drawn by the client - there is no file to copy
        util.printDebug(f"    Skipping built-in model {model_identifier}", debug)
        return

    # This protects against a circular reference in a model's chain
    # It doesn't help prevent copying the same parent model multiple times (harmless but slightly inefficient)
    if visited is None:
        visited = set()
    if model_file_relative in visited:
        return
    visited.add(model_file_relative)

    if (input_path / model_file_relative).exists():
        # The RP overrides this model, so we need to include it in the generated RP
        model_pack_path = input_path
        util.printDebug(f"    Copying model {model_file_relative}", debug)
        os.makedirs((output_path / model_file_relative).parent, exist_ok=True)
        shutil.copy(input_path / model_file_relative, output_path / model_file_relative)
    elif (vanilla_path / model_file_relative).exists():
        # The client already has this model, it is only read to find the
        # textures and the parent that the input RP might override
        model_pack_path = vanilla_path
        util.printDebug(f"    Reading vanilla model {model_file_relative}", debug)
    else:
        print(f"WARNING!!! Missing model file: {model_file_relative}", flush=True)
        return

    with open(model_pack_path / model_file_relative, "r") as f:
        data = json.load(f)

    copy_textures(input_path, output_path, data, debug)

    if "parent" in data:
        copy_model_chain(
            input_path, output_path, vanilla_path, data["parent"], debug, visited
        )


# Hands the model off for objmc conversion, and points the model entry at the
# converted model. The rotation is the part that belongs here: it lives on the
# model entry, not in the model file.
def convert_model_entry(
    input_path, output_path, model_path, model_entry, objmc_path, compress, debug
):
    # Every rotation is removed from the model entry, whether or not it gets
    # applied. The applied one is baked into the converted model, so the client
    # must not rotate it a second time.
    rotations = []
    for axis in ("x", "y", "z"):
        angle = model_entry.pop(axis, None)
        if angle is not None:
            rotations.append((axis, angle))

    # Only one axis can be baked in, so the rest are lost entirely
    if len(rotations) > 1:
        applied_axis, applied_angle = rotations[0]
        dropped = ", ".join(f"{axis}={angle}" for axis, angle in rotations[1:])
        print(
            f"WARNING!!! Multiple rotations for {model_path}: baking "
            f"{applied_axis}={applied_angle} and dropping {dropped}",
            flush=True,
        )

    rotation = rotations[0] if rotations else None

    objmc_conversion.convert_sodium_model(
        input_path, output_path, model_path, rotation, objmc_path, compress, debug
    )

    # create vanilla model name - the conversion gives the files it writes the
    # same suffix
    model_path += objmc_conversion.rotation_suffix(rotation)

    # update model entry
    model_entry["model"] = constants.MCME_NAMESPACE + ":" + model_path


def process(
    input_path, output_path, vanilla_path, model_entry, objmc_path, compress, debug
):
    model_identifier = model_entry.get("model", "")

    namespace, model_path = util.split_namespaced(model_identifier)

    if namespace == constants.MCME_NAMESPACE:
        convert_model_entry(
            input_path,
            output_path,
            model_path,
            model_entry,
            objmc_path,
            compress,
            debug,
        )
    else:
        copy_model_chain(
            input_path,
            output_path,
            vanilla_path,
            model_identifier,
            debug,
        )
