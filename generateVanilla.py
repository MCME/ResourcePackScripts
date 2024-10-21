import yaml
import subprocess
import os
import argparse
from pathlib import Path
from PIL import Image

import search_blockstate_files
import rotate_obj


def work_on_obj_file(filename):
    if filename.endswith('.obj'):
        print(f"work_on_obj_file: {filename}")

        rotations = search_blockstate_files.process_directory(input_path + '/assets/minecraft/blockstates',
                                                              'mcme:block/' + filename.replace('.obj', ''))

        meta_filename = filename.replace('.obj', '.objmeta')

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
            printDebug("Get texture from .mtl file: " + filename.replace('.obj', '.mtl'))
            with open(filename.replace('.obj', '.mtl'), 'r') as mtl_file:
                for mtl_line in mtl_file:
                    if mtl_line.startswith('map_Kd'):
                        texture = mtl_line.split()[1].strip()
                        break
        if texture:
            texture = input_path + "/assets/" + texture.replace(":", "/textures/") + ".png"

        if not output_model:
            output_model = filename.replace('.obj', '.json').replace('sodium/', 'vanilla/')
            printDebug("Use default output model: " + output_model)
        else:
            output_model = output_path + "/assets/" + output_model.replace(":", "/models/") + ".json"

        if not output_texture:
            output_texture = texture.replace(output_path + '/', output_path + '/')
            printDebug("Use default output texture: " + output_texture)
        else:
            output_texture = output_path + "/assets/" + output_texture.replace(":", "/textures/") + ".png"

        if texture and output_model and output_texture:

            output_model_dir = os.path.dirname(output_model)
            output_texture_dir = os.path.dirname(output_texture)

            if output_model_dir:
                os.makedirs(output_model_dir, exist_ok=True)
            if output_texture_dir:
                os.makedirs(output_texture_dir, exist_ok=True)

            for axis, angle in rotations:
                if axis == 'o':
                    rot_filename = filename
                    rot_output_model = output_model
                    rot_output_texture = output_texture
                else:
                    rot_filename = filename.replace('.obj', '_' + axis + '_' + angle + '.obj')
                    rot_output_model = output_model.replace('.json', '_' + axis + '_' + angle + '.json')
                    rot_output_texture = output_model.replace('.png', '_' + axis + '_' + angle + '.png')
                    rotate_obj.rotate_obj_file(filename, axis, angle)

                runList = ['python3', 'objmc/objmc.py', '--objs', rot_filename, '--texs', texture, '--offset',
                           offset[0], offset[1], offset[2], '--out', rot_output_model, rot_output_texture,
                           '--visibility', str(visibility)]
                if 'noshadow' in options:
                    runList.append('--noshadow')
                if 'flipuv' in options:
                    runList.append('--flipuv')

                printDebug("Running process script with " + str(runList))

                try:
                    result = subprocess.run(runList, check=True,
                                            stdout=subprocess.PIPE,  # Umleitung der normalen Ausgabe
                                            stderr=subprocess.PIPE)  # Umleitung der Fehlerausgabe
                    print("objmc Script result: ", result.returncode)
                except subprocess.CalledProcessError as e:
                    print(f"Error running process script: {e}")
                    print("Script output (stdout):", e.stdout.decode('utf-8') if e.stdout else "No stdout")
                    print("Script error output (stderr):", e.stderr.decode('utf-8') if e.stderr else "No stderr")
        else:
            print(f"Missing one of the required parameters for {filename}")


def printDebug(message):
    if debug:
        print(message)


Image.MAX_IMAGE_PIXELS = 1000000000
parser = argparse.ArgumentParser(description='Convert OBJ models to vanilla shader models.')

# Kommandozeilenargumente hinzufügen
parser.add_argument('input_path', help='Path to read OBJ models from')
parser.add_argument('output_path', help='Path to write vanilla shader models in.')
parser.add_argument('--changes',
                    help='Filename read changed files from. Only these files will be considered. Without this '
                         'argument all files are considered.',
                    default=None)
parser.add_argument('--debug', action='store_true', help='Create debug output.')

# Argumente parsen
args = parser.parse_args()

print(f'Source path: {args.input_path}')
print(f'Output path: {args.output_path}')
input_path = args.input_path
output_path = args.output_path
debug = args.debug

print("Generating vanilla files!")

if args.changes:
    changed_files_path = args.changes

    print(f"Processing changed .obj files read from: {changed_files_path}")

    with open(changed_files_path, 'r') as file:
        lines = file.readlines()

    for line in lines:
        work_on_obj_file(input_path + "/" + line.split('\t')[1].strip())
else:
    print(f"Processing all .obj files in: {input_path}")

    absolute_input_path = Path.cwd() / input_path
    for file_path in absolute_input_path.rglob('*'):
        if file_path.is_file():
            work_on_obj_file(str(file_path.relative_to(Path.cwd())))