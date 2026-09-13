import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import constants
import rotate_obj
import util
import yaml

converted_models = {}


# The suffix identifying a rotated variant of a model. Shared by the rotated
# .obj, the converted model and its texture, so they all have to agree.
def rotation_suffix(rotation: tuple[str, float] | None):
    if rotation is None:
        return ""
    axis, angle = rotation
    return f"_{axis}_{angle}"


def convert_model(
    input_path,
    output_path,
    model_path,
    rotation: tuple[str, float] | None,
    objmc_path,
    compress,
    debug,
):
    util.printDebug(f"    Converting model: {model_path} rotation: {rotation}", debug)
    vanilla_model_input_file = (
        input_path
        / constants.RELATIVE_SODIUM_MODELS_PATH
        / Path(model_path + constants.VANILLA_MODEL_EXTENSION)
    )
    if not vanilla_model_input_file.exists():
        print(
            "        WARNING! Expected model file not found: "
            + str(vanilla_model_input_file),
            flush=True,
        )
        return

    mtl_path = model_path
    obj_model_path = model_path

    with open(vanilla_model_input_file, "r") as f:
        data = json.load(f)
        if "model" in data:
            namespace, model_ref = util.split_namespaced(
                data["model"],
                constants.MCME_NAMESPACE,  # Q: Why is MCME the default here?
            )
            if namespace == constants.MCME_NAMESPACE:
                obj_model_path = model_ref
            else:
                print(
                    f"Unexpected namespace: {namespace} in mcme model file.",
                    flush=True,
                )
        else:
            return
        obj_model_path = obj_model_path.removeprefix("models/").removesuffix(
            constants.OBJ_MODEL_EXTENSION
        )

        if "mtl_override" in data:
            namespace, mtl_ref = util.split_namespaced(
                data["mtl_override"], constants.MCME_NAMESPACE
            )
            if namespace == constants.MCME_NAMESPACE:
                mtl_path = mtl_ref
            else:
                print(
                    f"Unexpected namespace: {namespace} in mcme mtl file.",
                    flush=True,
                )
        mtl_path = mtl_path.removeprefix("models/").removesuffix(
            constants.MTL_EXTENSION
        )

    # Check if obj model exists
    if not os.path.exists(
        input_path
        / constants.RELATIVE_SODIUM_MODELS_PATH
        / Path(obj_model_path + constants.OBJ_MODEL_EXTENSION)
    ):
        return

    # print(f"Model path: {model_path}")
    meta_file = (
        input_path
        / constants.RELATIVE_SODIUM_MODELS_PATH
        / Path(model_path + constants.OBJMETA_EXTENSION)
    )

    # default values
    options = []
    visibility = 7
    offset = ["-0.5", "0.0", "-0.5"]
    texture_path = None
    output_texture_path = None
    manual_parent_model = None
    omnidirectional_parent = False

    # read values from objmeta file
    if os.path.exists(meta_file):
        try:
            with open(meta_file, "r") as f:
                meta_data = yaml.safe_load(f)

            texture_path = meta_data.get("texture", None)
            output_texture_path = meta_data.get("output_texture", None)
            offset = meta_data.get("offset", "-0.5 0.0 -0.5").split()
            options = meta_data.get("options", [])
            visibility = meta_data.get("visibility", 7)
            manual_parent_model = meta_data.get("parent", None).split(":")[-1].strip()
            omnidirectional_parent = meta_data.get("omnidirectional_parent", False)

        except FileNotFoundError:
            print(f"Meta file not found for {model_path})")
        except yaml.YAMLError as exc:
            print(f"Error parsing objmeta file for {model_path}: {exc}")

    if not texture_path:
        # read texture path from .mtl file
        mtl_file = (
            input_path
            / constants.RELATIVE_SODIUM_MODELS_PATH
            / Path(mtl_path + constants.MTL_EXTENSION)
        )
        if mtl_file.exists():
            with open(mtl_file, "r") as f:
                for mtl_line in f:
                    if mtl_line.startswith("map_Kd"):
                        texture_path = mtl_line.split()[1].strip()
                        break
        else:
            print(f"Missing .mtl file {mtl_file}.")
            return

    if texture_path:
        relative_texture_path = constants.RELATIVE_SODIUM_TEXTURES_PATH
        namespace, texture_path = util.split_namespaced(
            texture_path, constants.MCME_NAMESPACE
        )
        if namespace == constants.VANILLA_NAMESPACE:
            relative_texture_path = constants.RELATIVE_VANILLA_TEXTURES_PATH
        elif namespace != constants.MCME_NAMESPACE:
            print(
                "WARNING!!! Unexpected texture namespace: "
                + namespace
                + "for "
                + texture_path,
                flush=True,
            )

        if not output_texture_path:
            output_texture_path = model_path
            # output texture will contain voxel data, needs to use model name
            # instead of texture name as several models might use same sodium texture
            # print("texture_path: "+texture_path)
            # printDebug("Use default output texture_path: " + output_texture_path)

        texture_file = (
            input_path
            / relative_texture_path
            / Path(texture_path + constants.TEXTURE_EXTENSION)
        )
        # print("output_texture_path: "+output_texture_path)
        # An unrotated model has an empty suffix, so these paths are the same
        # either way - only the .obj objmc reads from differs.
        model_suffix = rotation_suffix(rotation)
        model_file = (
            input_path
            / constants.RELATIVE_SODIUM_MODELS_PATH
            / Path(obj_model_path + model_suffix + constants.OBJ_MODEL_EXTENSION)
        )
        output_model_file = (
            output_path
            / constants.RELATIVE_SODIUM_MODELS_PATH
            / Path(model_path + model_suffix + constants.VANILLA_MODEL_EXTENSION)
        )
        output_texture_file = (
            output_path
            / constants.RELATIVE_SODIUM_TEXTURES_PATH
            / Path(output_texture_path + model_suffix + constants.TEXTURE_EXTENSION)
        )

        if rotation is not None:
            axis, angle = rotation
            # create rotated .obj file for objmc to read, deleted further down
            rotate_obj.rotate_obj_file(
                input_path
                / constants.RELATIVE_SODIUM_MODELS_PATH
                / Path(obj_model_path + constants.OBJ_MODEL_EXTENSION),
                model_file,
                axis,
                -angle,
            )

        # creating output folders if missing
        output_model_dir = os.path.dirname(output_model_file)
        output_texture_dir = os.path.dirname(output_texture_file)
        if output_model_dir:
            os.makedirs(output_model_dir, exist_ok=True)
        if output_texture_dir:
            os.makedirs(output_texture_dir, exist_ok=True)

        runList = [
            "python3",
            str(objmc_path),
            "--objs",
            str(model_file).replace("\\", "/"),
            "--texs",
            str(texture_file).replace("\\", "/"),
            "--offset",
            offset[0],
            offset[1],
            offset[2],
            "--out",
            str(output_model_file).replace("\\", "/"),
            str(output_texture_file).replace("\\", "/"),
            "--visibility",
            str(visibility),
        ]
        if "noshadow" in options:
            runList.append("--noshadow")
        if "flipuv" in options:
            runList.append("--flipuv")

        # util.printDebug("Running process script with texture output file:"
        # + str(output_texture_file).replace('\\', '/'), debug)
        # util.printDebug("Running process script with model output file:"
        # + str(output_model_file).replace('\\', '/'), debug)

        try:
            result = subprocess.run(
                runList, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            # sys.exit()

            util.printDebug("objmc Script result: " + str(result.returncode), False)

            with open(output_model_file, "r") as output_model_json:
                data = json.load(output_model_json)
                data["textures"]["0"] = (
                    constants.MCME_NAMESPACE + ":" + output_texture_path + model_suffix
                )  # .replace("\\", "/")
                data["textures"]["particle"] = (
                    constants.MCME_NAMESPACE + ":" + output_texture_path + model_suffix
                )
                del data["display"]
                if "gui_light" in data:
                    del data["gui_light"]
                util.remove_tintindex(data)
            # Check for already converted model file
            if manual_parent_model:
                del data["elements"]
                # del data['display']
                util.printDebug("        Manual parent: " + manual_parent_model, debug)
                original_manual_parent = manual_parent_model
                if rotation is not None and not omnidirectional_parent:
                    axis, angle = rotation
                    if axis == "y" and angle > 0:
                        if not bool(re.search(r"_[0-9]+$", manual_parent_model)):
                            manual_parent_model = manual_parent_model + "_1"
                        manual_parent_model = (
                            manual_parent_model + "_" + str(angle // 90 + 1)
                        )
                        util.printDebug(
                            "        Rotated parent: " + manual_parent_model, debug
                        )
                data["parent"] = constants.MCME_NAMESPACE + ":" + manual_parent_model
                if manual_parent_model not in converted_models:
                    override_model_file = (
                        input_path
                        / constants.RELATIVE_VANILLA_OVERRIDES_PATH
                        / constants.RELATIVE_SODIUM_MODELS_PATH
                        / Path(manual_parent_model + constants.VANILLA_MODEL_EXTENSION)
                    )
                    if override_model_file.exists():
                        shutil.copy(
                            override_model_file,
                            output_path
                            / constants.RELATIVE_SODIUM_MODELS_PATH
                            / Path(
                                manual_parent_model + constants.VANILLA_MODEL_EXTENSION
                            ),
                        )
                    else:
                        print(
                            f"        WARNING!!! Expected parent file {manual_parent_model} not found! Using: "
                            + original_manual_parent,
                            flush=True,
                        )
                        data["parent"] = (
                            constants.MCME_NAMESPACE + ":" + original_manual_parent
                        )
                        if original_manual_parent not in converted_models:
                            override_model_file = (
                                input_path
                                / constants.RELATIVE_VANILLA_OVERRIDES_PATH
                                / constants.RELATIVE_SODIUM_MODELS_PATH
                                / Path(
                                    original_manual_parent
                                    + constants.VANILLA_MODEL_EXTENSION
                                )
                            )
                            if override_model_file.exists():
                                shutil.copy(
                                    override_model_file,
                                    output_path
                                    / constants.RELATIVE_SODIUM_MODELS_PATH
                                    / Path(
                                        original_manual_parent
                                        + constants.VANILLA_MODEL_EXTENSION
                                    ),
                                )
                            else:
                                print(
                                    f"        ERROR!!! Expected parent file {original_manual_parent} not found!",
                                    flush=True,
                                )
                    converted_models[manual_parent_model] = constants.PARENT_DONE_VALUE
            elif model_path in converted_models:
                del data["elements"]
                # del data['display']
                data["parent"] = (
                    constants.MCME_NAMESPACE
                    + ":"
                    + model_path
                    + constants.PARENT_SUFFIX
                )
                if converted_models[model_path] != constants.PARENT_DONE_VALUE:
                    # link previously converted model to new parent
                    with open(converted_models[model_path], "r") as first_model_json:
                        first_model_data = json.load(first_model_json)
                        parent_model_data = first_model_data.copy()
                        del parent_model_data["textures"]
                        del first_model_data["elements"]
                        # del first_model_data['display']
                        first_model_data["parent"] = (
                            constants.MCME_NAMESPACE
                            + ":"
                            + model_path
                            + constants.PARENT_SUFFIX
                        )
                    with open(converted_models[model_path], "w") as first_model_json:
                        if compress:
                            json.dump(
                                first_model_data,
                                first_model_json,
                                separators=(",", ":"),
                            )  # type: ignore
                        else:
                            json.dump(first_model_data, first_model_json, indent=4)  # type: ignore
                    parent_model_file = (
                        output_path
                        / constants.RELATIVE_SODIUM_MODELS_PATH
                        / Path(
                            model_path
                            + constants.PARENT_SUFFIX
                            + constants.VANILLA_MODEL_EXTENSION
                        )
                    )
                    with parent_model_file.open("w") as parent_model_json:
                        if compress:
                            json.dump(
                                parent_model_data,
                                parent_model_json,
                                separators=(",", ":"),
                            )  # type: ignore
                        else:
                            json.dump(parent_model_data, parent_model_json, indent=4)  # type: ignore
                converted_models[model_path] = constants.PARENT_DONE_VALUE
            else:
                converted_models[model_path] = output_model_file
            with open(output_model_file, "w") as output_model_json:
                if compress:
                    json.dump(data, output_model_json, separators=(",", ":"))  # type: ignore
                else:
                    json.dump(data, output_model_json, indent=4)  # type: ignore
        except subprocess.CalledProcessError as e:
            print(f"Error running process script: {e}")
            print(
                "Script output (stdout):",
                e.stdout.decode("utf-8") if e.stdout else "No stdout",
            )
            print(
                "Script error output (stderr):",
                e.stderr.decode("utf-8") if e.stderr else "No stderr",
                flush=True,
            )

        if rotation is not None:
            # remove the temporary rotated .obj created above
            Path(model_file).unlink()

    else:
        print(f"        Missing texture for {model_path}", flush=True)


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


# Converts the .obj model to a Vanilla shader model, baking any rotation into
# it, and points the model entry at the converted model.
def convert_sodium_model(
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

    convert_model(
        input_path, output_path, model_path, rotation, objmc_path, compress, debug
    )

    # create vanilla model name - convert_model gives the files it writes the
    # same suffix
    model_path += rotation_suffix(rotation)

    # update model entry
    model_entry["model"] = constants.MCME_NAMESPACE + ":" + model_path


def process(
    input_path, output_path, vanilla_path, model_entry, objmc_path, compress, debug
):
    model_identifier = model_entry.get("model", "")

    namespace, model_path = util.split_namespaced(model_identifier)

    if namespace == constants.MCME_NAMESPACE:
        convert_sodium_model(
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
