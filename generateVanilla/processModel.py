import os
from pathlib import Path
import json
import shutil

import yaml

import constants
import generateVanilla


def convert_model(model_path, axis, angle):
    meta_file = generateVanilla.input_path / constants.RELATIVE_SODIUM_MODELS_PATH \
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
        # printDebug("Get texture_path from .mtl file: " + filename.replace('.obj', '.mtl'))
        with open(generateVanilla.input_path / constants.RELATIVE_SODIUM_MODELS_PATH
                                             / Path(model_path + constants.MTL_EXTENSION), 'r') as f:
            for mtl_line in f:
                if mtl_line.startswith('map_Kd'):
                    texture_path = mtl_line.split()[1].strip()
                    break
    if texture_path:
        texture_file = generateVanilla.input_path / constants.RELATIVE_SODIUM_TEXTURES_PATH \
                                                  / Path(texture_path + constants.TEXTURE_EXTENSION)
    if not output_texture_path:
        output_texture_file = generateVanilla.output_path / constants.RELATIVE_SODIUM_TEXTURES_PATH \
                                                          / Path(texture_path + constants.TEXTURE_EXTENSION)
        # printDebug("Use default output texture_path: " + output_texture_path)
    else:
        output_texture_file = generateVanilla.output_path / constants.RELATIVE_SODIUM_TEXTURES_PATH \
                                                          / Path(output_texture_path + constants.TEXTURE_EXTENSION)

    output_model_file = generateVanilla.output_path / constants.RELATIVE_SODIUM_MODELS_PATH \
                                                    / Path(model_path + constants.VANILLA_MODEL_EXTENSION)

    if texture_path:

        output_model_dir = os.path.dirname(output_model_file)
        output_texture_dir = os.path.dirname(output_texture_file)

        if output_model_dir:
            os.makedirs(output_model_dir, exist_ok=True)
        if output_texture_dir:
            os.makedirs(output_texture_dir, exist_ok=True)

        # print(str(rotations))
        for axis, angle in rotations:
            if axis == 'o':
                rot_filename = str(input_path / relative_filepath)
                rot_output_model = output_model_path
                rot_output_texture = output_texture_path
                is_rotated_obj = False
            else:
                rot_filename = str(input_path / relative_filepath) \
                    .replace('.obj', '_' + axis + '_' + str(angle) + '.obj')
                rot_output_model = output_model_path.replace('.json', '_' + axis + '_' + str(angle) + '.json')
                rot_output_texture = output_texture_path.replace('.png', '_' + axis + '_' + str(angle) + '.png')
                rotate_obj.rotate_obj_file(input_path, output_path, relative_filepath, axis, angle)
                is_rotated_obj = True

            runList = ['python3', str(objmc_path), '--objs', rot_filename.replace('\\', '/'),
                       '--texs', texture_path.replace('\\', '/'),
                       '--offset', offset[0], offset[1], offset[2],
                       '--out', rot_output_model.replace('\\', '/'), rot_output_texture.replace('\\', '/'),
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
                # print("objmc Script result: ", result.returncode)
                with open(rot_output_model, 'r') as output_model_json:
                    data = json.load(output_model_json)
                    data['textures']['0'] \
                        = "mcme:" + str(Path(rot_output_texture)
                                        .relative_to(output_path / Path("assets/mcme/textures"))) \
                        .replace("\\", "/")
                with open(rot_output_model, 'w') as output_model_json:
                    json.dump(data, output_model_json, indent=4)
                    # json.dump(data, output_model_json, separators=(',', ':'))
            except subprocess.CalledProcessError as e:
                print(f"Error running process script: {e}")
                print("Script output (stdout):", e.stdout.decode('utf-8') if e.stdout else "No stdout")
                print("Script error output (stderr):",
                      e.stderr.decode('utf-8') if e.stderr else "No stderr", flush=True)

            if is_rotated_obj:
                Path(rot_filename).unlink()

    else:
        print(f"Missing one of the required parameters for {filename}")
    return blockstate_files


# convert model entry
def process(model_data):
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
            convert_model(model_path, "x", x)
            namespace_and_path += f"_x_{x}"
        elif y is not None:
            convert_model(model_path, "y", y)
            namespace_and_path += f"_y_{y}"
        elif z is not None:
            convert_model(model_path, "z", z)
            namespace_and_path += f"_z_{z}"
        else:
            convert_model(model_path, "o", 0)

        # update model entry
        model_data["model"] = constants.MCME_NAMESPACE + ":" + model_path

    else:
        # copy vanilla model and textures to output folder
        model_path = namespace_and_path[-1]
        model_file_relative = generateVanilla.input_path / constants.RELATIVE_VANILLA_MODELS_PATH \
                                                         / Path(model_path + constants.VANILLA_MODEL_EXTENSION)
        with open(generateVanilla.input_path / model_file_relative, 'r') as f:
            data = json.load(f)
            for texture_name, texture_path in data["textures"].items():
                texture_file_relative = constants.RELATIVE_VANILLA_TEXTURES_PATH \
                                        / Path(texture_path + constants.TEXTURE_EXTENSION)
                os.makedirs((generateVanilla.output_path / texture_file_relative).parent)
                shutil.copy(generateVanilla.input_path / texture_file_relative,
                            generateVanilla.output_path / texture_file_relative)
        os.makedirs((generateVanilla.output_path / model_file_relative).parent)
        shutil.copy(generateVanilla.input_path / model_file_relative,
                    generateVanilla.output_path / model_file_relative)
