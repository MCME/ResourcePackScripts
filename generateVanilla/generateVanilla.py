import yaml
import json
import subprocess
import os
import argparse
from pathlib import Path
from PIL import Image

import constants
import processBlockstate
import search_blockstate_files
import generateVanillaBlockstateFiles
import rotate_obj

relative_blockstate_path = "assets/minecraft/blockstates"
relative_sodium_models_path = "assets/mcme/models"
relative_sodium_textures_path = "assets/mcme/textures"
relative_vanilla_models_path = "assets/minecraft/models"
relative_vanilla_textures_path = "assets/minecraft/textures"


def work_on_obj_file(relative_filepath):
    filename = relative_filepath.name
    # printDebug(" ")
    printDebug(f"work_on_obj_file: {relative_filepath}")
    # printDebug(f"input path is: {input_path}")
    blockstate_path = input_path / Path('assets/minecraft/blockstates')
    # printDebug(f"blockstates path is: {blockstate_path}")
    blockstate_files_and_rotations = search_blockstate_files.process_directory(blockstate_path,
                                                                               'mcme:block/' + filename.replace('.obj',
                                                                                                                ''))
    rotations = blockstate_files_and_rotations[0]
    blockstate_files = blockstate_files_and_rotations[1]

    # if rotations list is empty no blockstate file is linking this model, no vanilla model created in this case
    if not blockstate_files:
        print("Model not linked by any blockstate file. Skipped!")
        return []

    meta_filename = str(input_path / relative_filepath).replace('.obj', '.objmeta')

    # default values
    options = []
    visibility = 7
    offset = ['0.0', '0.0', '0.0']
    texture = None
    output_model = None
    output_texture = None

    # read values from objmeta file
    if os.path.exists(meta_filename):
        try:
            with open(meta_filename, 'r') as meta_file:
                meta_data = yaml.safe_load(meta_file)

            texture = meta_data.get('texture', None)
            output_model = meta_data.get('output_model', None)
            output_texture = meta_data.get('output_texture', None)
            offset = meta_data.get('offset', '0.0 0.0 0.0').split()
            options = meta_data.get('options', [])
            visibility = meta_data.get('visibility', 7)

        except FileNotFoundError:
            print(f"Meta file not found for {filename} ({meta_filename})")
        except yaml.YAMLError as exc:
            print(f"Error parsing YAML file {meta_filename}: {exc}")

    if not texture:
        # printDebug("Get texture from .mtl file: " + filename.replace('.obj', '.mtl'))
        with open(str(input_path / relative_filepath).replace('.obj', '.mtl'), 'r') as mtl_file:
            for mtl_line in mtl_file:
                if mtl_line.startswith('map_Kd'):
                    texture = mtl_line.split()[1].strip()
                    break
    if texture:
        texture = str(input_path) + "/assets/" + texture.replace(":", "/textures/") + ".png"

    if not output_model:
        output_model = str(output_path / relative_filepath).replace('.obj', '.json')
        # printDebug("Use default output model: " + output_model)
    else:
        output_model = str(output_path) + "/assets/" + output_model.replace(":", "/models/") + ".json"

    if not output_texture:
        output_texture = texture.replace(str(input_path) + '/', str(output_path) + '/')
        # printDebug("Use default output texture: " + output_texture)
    else:
        output_texture = str(output_path) + "/assets/" + output_texture.replace(":", "/textures/") + ".png"

    if texture and output_model and output_texture:

        output_model_dir = os.path.dirname(output_model)
        output_texture_dir = os.path.dirname(output_texture)

        if output_model_dir:
            os.makedirs(output_model_dir, exist_ok=True)
        if output_texture_dir:
            os.makedirs(output_texture_dir, exist_ok=True)

        # print(str(rotations))
        for axis, angle in rotations:
            if axis == 'o':
                rot_filename = str(input_path / relative_filepath)
                rot_output_model = output_model
                rot_output_texture = output_texture
                is_rotated_obj = False
            else:
                rot_filename = str(input_path / relative_filepath)\
                    .replace('.obj', '_' + axis + '_' + str(angle) + '.obj')
                rot_output_model = output_model.replace('.json', '_' + axis + '_' + str(angle) + '.json')
                rot_output_texture = output_texture.replace('.png', '_' + axis + '_' + str(angle) + '.png')
                rotate_obj.rotate_obj_file(input_path / relative_filepath, Path(rot_filename), axis, angle)
                is_rotated_obj = True

            runList = ['python3', str(objmc_path), '--objs', rot_filename.replace('\\', '/'),
                       '--texs', texture.replace('\\', '/'),
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
                printDebug("objmc Script result: " + str(result.returncode))
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


def printDebug(message):
    if debug:
        print(message, flush=True)


Image.MAX_IMAGE_PIXELS = 1000000000
parser = argparse.ArgumentParser(description='Convert OBJ models to vanilla shader models.')

# add command line arguments
parser.add_argument('input_path', help='Path to read OBJ models from')
parser.add_argument('output_path', help='Path to write vanilla shader models in.')
parser.add_argument('vanilla_path', help='Path to read vanilla RP from.')
parser.add_argument('--changes',
                    help='Filename read changed files from. Only these files will be considered. Without this '
                         'argument all files are considered.',
                    default=None)
parser.add_argument('--limit',
                    help='Limit for number of alternate models for one blockstate. Defaults to no limit.',
                    default="-1")
parser.add_argument('--objmc',
                    help='Path to objmc script. Defaults to working directory.',
                    default='objmc.py')
parser.add_argument('--debug', action='store_true', help='Create debug output.')
parser.add_argument('--compress', action='store_true', help='Compress generated .json files.')

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

print("Generating vanilla resource pack!")

if args.changes:
    changed_files_path = args.changes

    print(f"Processing changed .obj files read from: {changed_files_path}")

    with open(changed_files_path, 'r') as file:
        lines = file.readlines()

    for line in lines:
        blockstate_file_list = work_on_obj_file(input_path / Path(line.split('\t')[1].strip()))
        generateVanillaBlockstateFiles.convert_blockstate_files(blockstate_file_list, input_path, output_path, limit)
else:
    print(f"Processing Sodium RP in: {input_path}")

    for blockstate_file in (vanilla_path / constants.RELATIVE_BLOCKSTATE_PATH)\
                        .glob("*"+constants.BLOCKSTATE_EXTENSION):
        if blockstate_file.is_file():
            processBlockstate.process(input_path, output_path, vanilla_path, blockstate_file.name, limit, compress, objmc_path, debug)
