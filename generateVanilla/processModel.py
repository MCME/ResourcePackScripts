import os
import subprocess
from pathlib import Path
import json
import shutil

import yaml

import constants
import rotate_obj


def convert_model(input_path, output_path, model_path, axis, angle, objmc_path, compress, debug):
    with open(input_path / constants.RELATIVE_SODIUM_MODELS_PATH
              / Path(model_path + constants.VANILLA_MODEL_EXTENSION), 'r') as f:
        data = json.load(f)
        if "model" in data:
            model_data = data["model"].split(":")
            if model_data[0] == constants.MCME_NAMESPACE:
                model_path = model_data[1]
            elif len(model_data) == 1:
                model_path = model_data[0]
            else:
                print("Unexpected namespace: {model_data[0]} in mcme model file.")
        else:
            return
        model_path = model_path.removeprefix("models/").removesuffix(constants.OBJ_MODEL_EXTENSION)

    # print(f"Model path: {model_path}")
    meta_file = input_path / constants.RELATIVE_SODIUM_MODELS_PATH \
                / Path(model_path + constants.OBJMETA_EXTENSION)

    # default values
    options = []
    visibility = 7
    offset = ['0.0', '0.0', '0.0']
    texture_path = None
    output_texture_path = None

    # read values from objmeta file
    if os.path.exists(meta_file):
        try:
            with open(meta_file, 'r') as f:
                meta_data = yaml.safe_load(f)

            texture_path = meta_data.get('texture', None)
            output_texture_path = meta_data.get('output_texture', None)
            offset = meta_data.get('offset', '0.0 0.0 0.0').split()
            options = meta_data.get('options', [])
            visibility = meta_data.get('visibility', 7)

        except FileNotFoundError:
            print(f"Meta file not found for {model_path})")
        except yaml.YAMLError as exc:
            print(f"Error parsing objmeta file for {model_path}: {exc}")

    if not texture_path:
        # read texture path from .mtl file
        mtl_file = input_path / constants.RELATIVE_SODIUM_MODELS_PATH / Path(model_path + constants.MTL_EXTENSION)
        if mtl_file.exists():
            with open(mtl_file, 'r') as f:
                for mtl_line in f:
                    if mtl_line.startswith('map_Kd'):
                        texture_path = mtl_line.split()[1].strip()
                        break
        else:
            print(f"Missing .mtl file {mtl_file}.")
            return

    if texture_path:
        relative_texture_path = constants.RELATIVE_SODIUM_TEXTURES_PATH
        if ":" in texture_path:
            texture_split = texture_path.split(':')
            namespace = texture_split[0]
            texture_name = texture_split[1]
            if namespace == constants.VANILLA_NAMESPACE:
                relative_texture_path = constants.RELATIVE_VANILLA_TEXTURES_PATH
            elif namespace != constants.MCME_NAMESPACE:
                print("WARNING!!! Unexpected texture namespace: "+namespace+"for "+texture_name)
            texture_path = texture_name

        if not output_texture_path:
            output_texture_path = texture_path
            # print("texture_path: "+texture_path)
            # printDebug("Use default output texture_path: " + output_texture_path)

        texture_file = input_path / relative_texture_path \
                       / Path(texture_path + constants.TEXTURE_EXTENSION)
        # print("output_texture_path: "+output_texture_path)
        if axis == 'o':
            model_suffix = ""
            model_file = input_path / constants.RELATIVE_SODIUM_MODELS_PATH \
                         / Path(model_path + constants.OBJ_MODEL_EXTENSION)
            output_model_file = output_path / constants.RELATIVE_SODIUM_MODELS_PATH \
                                / Path(model_path + constants.VANILLA_MODEL_EXTENSION)
            output_texture_file = output_path / constants.RELATIVE_SODIUM_TEXTURES_PATH \
                                  / Path(output_texture_path + constants.TEXTURE_EXTENSION)
            is_rotated_obj = False
        else:
            model_suffix = '_' + axis + '_' + str(angle)
            model_file = input_path / constants.RELATIVE_SODIUM_MODELS_PATH \
                         / Path(model_path + model_suffix + constants.OBJ_MODEL_EXTENSION)

            # create rotated .obj file
            rotate_obj.rotate_obj_file(input_path / constants.RELATIVE_SODIUM_MODELS_PATH /
                                       Path(model_path + constants.OBJ_MODEL_EXTENSION), model_file, axis, angle)

            output_model_file = output_path / constants.RELATIVE_SODIUM_MODELS_PATH \
                                / Path(model_path + model_suffix + constants.VANILLA_MODEL_EXTENSION)
            output_texture_file = output_path / constants.RELATIVE_SODIUM_TEXTURES_PATH \
                                  / Path(output_texture_path + model_suffix + constants.TEXTURE_EXTENSION)
            is_rotated_obj = True

        # creating output folders if missing
        output_model_dir = os.path.dirname(output_model_file)
        output_texture_dir = os.path.dirname(output_texture_file)
        if output_model_dir:
            os.makedirs(output_model_dir, exist_ok=True)
        if output_texture_dir:
            os.makedirs(output_texture_dir, exist_ok=True)

        runList = ['python3', str(objmc_path), '--objs', str(model_file).replace('\\', '/'),
                   '--texs', str(texture_file).replace('\\', '/'),
                   '--offset', offset[0], offset[1], offset[2],
                   '--out', str(output_model_file).replace('\\', '/'), str(output_texture_file).replace('\\', '/'),
                   '--visibility', str(visibility)]
        if 'noshadow' in options:
            runList.append('--noshadow')
        if 'flipuv' in options:
            runList.append('--flipuv')

        # printDebug("Running process script with " + str(runList))

        try:
            result = subprocess.run(runList, check=True,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE)
            # if debug:
            #    print("objmc Script result: " + str(result.returncode))
            with open(output_model_file, 'r') as output_model_json:
                data = json.load(output_model_json)
                data['textures']['0'] \
                    = "mcme:" + output_texture_path + model_suffix + constants.TEXTURE_EXTENSION  # .replace("\\", "/")
            with open(output_model_file, 'w') as output_model_json:
                if compress:
                    json.dump(data, output_model_json, separators=(',', ':'))
                else:
                    json.dump(data, output_model_json, indent=4)
        except subprocess.CalledProcessError as e:
            print(f"Error running process script: {e}")
            print("Script output (stdout):", e.stdout.decode('utf-8') if e.stdout else "No stdout")
            print("Script error output (stderr):",
                  e.stderr.decode('utf-8') if e.stderr else "No stderr", flush=True)

        if is_rotated_obj:
            Path(model_file).unlink()

    else:
        print(f"Missing texture for {model_path}")


def copy_textures(model_path, texture_path, output_path, model_file_relative):
    with open(model_path / model_file_relative, 'r') as f:
        data = json.load(f)
        # print(f"copy_textures: {model_path} {texture_path} {model_file_relative}")
        if "textures" in data:
            for texture_name, texture_filename in data["textures"].items():
                relative_path = constants.RELATIVE_VANILLA_TEXTURES_PATH
                if ":" in texture_filename:
                    texture_split = texture_filename.split(":")
                    if texture_split[0] == constants.VANILLA_NAMESPACE:
                        texture_filename = texture_split[1]
                    elif texture_split[0] == constants.MCME_NAMESPACE:
                        texture_filename = texture_split[1]
                        relative_path = constants.RELATIVE_SODIUM_TEXTURES_PATH
                    else:
                        print(f'WARNING!!! Unexpected texture namespace {texture_split[0]} for {texture_filename}')
                        return

                texture_file_relative = relative_path \
                                        / Path(texture_filename + constants.TEXTURE_EXTENSION)
                os.makedirs((output_path / texture_file_relative).parent, exist_ok=True)
                texture_file = texture_path / texture_file_relative
                if texture_file.exists():
                    shutil.copy(texture_file, output_path / texture_file_relative)


# convert model entry
def process(input_path, output_path, vanilla_path, model_data, objmc_path, compress, debug):
    namespace_and_path = model_data.get("model", "").split(":")

    if namespace_and_path[0] == constants.MCME_NAMESPACE:
        # convert .obj model to Vanilla shader model
        model_path = namespace_and_path[1]

        # check if one key of "x", "y", oder "z" exists
        x = model_data.pop("x", None)
        y = model_data.pop("y", None)
        z = model_data.pop("z", None)

        # create vanilla model name
        if x is not None:
            convert_model(input_path, output_path, model_path, "x", x, objmc_path, compress, debug)
            namespace_and_path += f"_x_{x}"
        elif y is not None:
            convert_model(input_path, output_path, model_path, "y", y, objmc_path, compress, debug)
            namespace_and_path += f"_y_{y}"
        elif z is not None:
            convert_model(input_path, output_path, model_path, "z", z, objmc_path, compress, debug)
            namespace_and_path += f"_z_{z}"
        else:
            convert_model(input_path, output_path, model_path, "o", 0, objmc_path, compress, debug)

        # update model entry
        model_data["model"] = constants.MCME_NAMESPACE + ":" + model_path

    else:
        # copy vanilla model and textures to output folder
        model_path = namespace_and_path[-1]
        model_file_relative = constants.RELATIVE_VANILLA_MODELS_PATH \
                              / Path(model_path + constants.VANILLA_MODEL_EXTENSION)
        if (input_path / model_file_relative).exists():
            copy_textures(input_path, input_path, output_path, model_file_relative)
            os.makedirs((output_path / model_file_relative).parent, exist_ok=True)
            # print(f'Model relative path: {model_file_relative}')
            shutil.copy(input_path / model_file_relative,
                        output_path / model_file_relative)
        else:
            # read textures to copy from vanilla pack file.
            if (vanilla_path / model_file_relative).exists():
                copy_textures(vanilla_path, input_path, output_path, model_file_relative)
            else:
                print(f'WARNING!!! Missing model file: {model_file_relative}')
