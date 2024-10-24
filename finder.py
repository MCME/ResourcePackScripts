import os
# import shutil
import json
import sys

blockstates_dir = 'blockstates'
vanilla_blockstates_dir = 'vanilla_blockstates'
models_dir = 'models'
vanilla_models_dir = 'vanilla_models'
textures_dir = 'textures'
unlinked_models_dir = 'unlinked_models'
unlinked_textures_dir = 'unlinked_textures'

linked_model_paths = set()


def add_linked_model(model, model_to_test, blockstate_path):
    model_path = model.get('model', None)
    if model_path:
        model_path = model_path.replace('minecraft:', '').replace('block/', '')
        linked_model_paths.add(os.path.join(models_dir, 'block', f"{model_path}.json"))
        # print(model_path,"-------",model_to_test)
        if model_path == model_to_test:
            print("Linked in blockstate file: ", blockstate_path)


def collect_linked_parent_models(models_block_dir, custom_model_block_dir, excluded_files, model_to_test):
    for filename in os.listdir(models_block_dir):
        if filename.endswith('.json') and filename not in excluded_files:
            model_path = os.path.join(models_block_dir, filename)

            # print(model_path)
            if os.path.join(custom_model_block_dir, filename) in linked_model_paths:
                with open(model_path, 'r') as file:
                    data = json.load(file)
                    if 'parent' in data:
                        parent_model = data['parent']
                        linked_model_paths.add(
                            os.path.join(models_dir, 'block', f"{parent_model.replace('block/', '')}.json"))
                        # print(parent_model,"-------",model_to_test)
                        if parent_model.replace('block/', '') == model_to_test:
                            print("Linked as parent in: ", model_path)


def collect_linked_model_paths_from_blockstate_files(blockstates_directory, blockstate_files, model_to_test):
    for filename in blockstate_files:
        if "parent" in filename:
            print(f"Skipping file with 'parent' in its name: {filename}")
            continue

        if filename.endswith('.json'):
            blockstate_path = os.path.join(blockstates_directory, filename)
            # print(f"Processing blockstate file: {blockstate_path}")

            try:
                with open(blockstate_path, 'r') as file:
                    data = json.load(file)

                    if 'variants' in data:
                        for variant_key, variant in data['variants'].items():
                            if isinstance(variant, dict):
                                add_linked_model(variant, model_to_test, blockstate_path)
                            else:
                                for model in variant:
                                    add_linked_model(model, model_to_test, blockstate_path)

                    if 'multipart' in data:
                        for part in data['multipart']:
                            if 'apply' in part:
                                apply = part['apply']
                                if isinstance(apply, dict):
                                    add_linked_model(apply, model_to_test, blockstate_path)
                                else:
                                    for model in apply:
                                        add_linked_model(model, model_to_test, blockstate_path)

            except json.JSONDecodeError as e:
                print(f"Error decoding JSON in file {blockstate_path}: {e}")
            except Exception as e:
                print(f"Unexpected error processing file {blockstate_path}: {e}")


def collect_linked_model_paths(model_to_test):
    blockstate_files = os.listdir(blockstates_dir)
    print("Testing custom blockstate files.")
    collect_linked_model_paths_from_blockstate_files(blockstates_dir, blockstate_files, model_to_test)
    vanilla_blockstate_files = os.listdir(vanilla_blockstates_dir)
    for file in blockstate_files:
        if file in vanilla_blockstate_files:
            vanilla_blockstate_files.remove(file)
    print("Testing vanilla blockstate files.")
    collect_linked_model_paths_from_blockstate_files(vanilla_blockstates_dir, vanilla_blockstate_files, model_to_test)

    # Collect parent models and textures from models/block directory
    models_block_dir = os.path.join(models_dir, 'block')
    vanilla_models_block_dir = os.path.join(vanilla_models_dir, 'block')
    print('Testing parent models.')
    collect_linked_parent_models(models_block_dir, models_block_dir, set(), model_to_test)
    print('Testing parent models of vanilla models.')
    collect_linked_parent_models(vanilla_models_block_dir, models_block_dir, os.listdir(models_block_dir),
                                 model_to_test)


def main(model_to_test):
    # Get all linked model paths from blockstates and parent models from models/block
    collect_linked_model_paths(model_to_test)


if __name__ == "__main__":
    main(sys.argv[1])
