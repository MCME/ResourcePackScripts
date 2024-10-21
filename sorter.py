import os
import shutil
import json


blockstates_dir = 'blockstates'
vanilla_blockstates_dir = 'vanilla_blockstates'
models_dir = 'models'
vanilla_models_dir = 'vanilla_models'
textures_dir = 'textures'
unlinked_models_dir = 'unlinked_models'
unlinked_textures_dir = 'unlinked_textures'

linked_model_paths = set()
linked_texture_paths = set()


def ensure_unlinked_folder_exists():
    if not os.path.exists(unlinked_models_dir):
        os.makedirs(unlinked_models_dir)
    if not os.path.exists(unlinked_textures_dir):
        os.makedirs(unlinked_textures_dir)


def add_linked_model(model):
    model_path = model.get('model', None)
    if model_path:
        model_path = model_path.replace('minecraft:', '').replace('block/', '')
        linked_model_paths.add(os.path.join(models_dir, 'block', f"{model_path}.json"))


def collect_linked_parent_models(models_block_dir, custom_model_block_dir, excluded_files):
    for filename in os.listdir(models_block_dir):
        if filename.endswith('.json') and filename not in excluded_files:
            model_path = os.path.join(models_block_dir, filename)

            print(model_path)
            if os.path.join(custom_model_block_dir, filename) in linked_model_paths:
                with open(model_path, 'r') as file:
                    data = json.load(file)
                    if 'parent' in data:
                        parent_model = data['parent']
                        linked_model_paths.add(os.path.join(models_dir, 'block', f"{parent_model.replace('block/', '')}.json"))


def collect_linked_textures(models_block_dir, custom_model_block_dir, excluded_files):
    for filename in os.listdir(models_block_dir):
        if filename.endswith('.json') and filename not in excluded_files:
            model_path = os.path.join(models_block_dir, filename)

            print(model_path)
            if os.path.join(custom_model_block_dir, filename) in linked_model_paths:
                with open(model_path, 'r') as file:
                    data = json.load(file)
                    if 'textures' in data:
                        for texture_path in data['textures'].values():
                            linked_texture_paths.add(os.path.join(textures_dir, 'block', f"{texture_path.replace('block/', '')}.png"))


def collect_linked_model_paths_from_blockstate_files(blockstates_dir, blockstate_files):
    for filename in blockstate_files:
        if "parent" in filename:
            print(f"Skipping file with 'parent' in its name: {filename}")
            continue
        
        if filename.endswith('.json'):
            blockstate_path = os.path.join(blockstates_dir, filename)
            print(f"Processing blockstate file: {blockstate_path}")
            
            try:
                with open(blockstate_path, 'r') as file:
                    data = json.load(file)
                    
                    if 'variants' in data:
                        for variant_key, variant in data['variants'].items():
                            if isinstance(variant, dict):
                                add_linked_model(variant)
                            else:
                                for model in variant:
                                    add_linked_model(model)

                    if 'multipart' in data:
                        for part in data['multipart']:
                            if 'apply' in part:
                                apply = part['apply']
                                if isinstance(apply, dict):
                                    add_linked_model(apply)
                                else:
                                    for model in apply:
                                        add_linked_model(model)

            except json.JSONDecodeError as e:
                print(f"Error decoding JSON in file {blockstate_path}: {e}")
            except Exception as e:
                print(f"Unexpected error processing file {blockstate_path}: {e}")


def collect_linked_model_paths():
    blockstate_files = os.listdir(blockstates_dir)
    print("Collecting from custom blockstate files.")
    collect_linked_model_paths_from_blockstate_files(blockstates_dir, blockstate_files)
    vanilla_blockstate_files = os.listdir(vanilla_blockstates_dir)
    for file in blockstate_files:
        if file in vanilla_blockstate_files:
            vanilla_blockstate_files.remove(file)
    print("Collecting from vanilla blockstate files.")
    collect_linked_model_paths_from_blockstate_files(vanilla_blockstates_dir, vanilla_blockstate_files)

    # Collect parent models and textures from models/block directory
    models_block_dir = os.path.join(models_dir, 'block')
    vanilla_models_block_dir = os.path.join(vanilla_models_dir, 'block')
    print('Collecting parent models.')
    collect_linked_parent_models(models_block_dir, models_block_dir, set())
    print('Collecting parent models of vanilla models.')
    collect_linked_parent_models(vanilla_models_block_dir, models_block_dir, os.listdir(models_block_dir))
    print('Collecting textures.')
    collect_linked_textures(models_block_dir, models_block_dir, set())
    print('Collecting textures of vanilla models.')
    collect_linked_textures(vanilla_models_block_dir, models_block_dir, os.listdir(models_block_dir))


def main():
    # Ensure the unlinked_models folder exists
    ensure_unlinked_folder_exists()

    # Get all linked model paths from blockstates and parent models from models/block
    collect_linked_model_paths()
    print(f"Total linked model paths: {len(linked_model_paths)}")
    print(f"Linked model paths: {linked_model_paths}")
    print(f"Total linked texture paths: {len(linked_texture_paths)}")
    print(f"Linked texture paths: {linked_texture_paths}")

    # Move unlinked model files to unlinked_models folder
    models_block_dir = os.path.join(models_dir, 'block')
    for root, _, files in os.walk(models_block_dir):
        for filename in files:
            if filename.endswith('.json'):
                model_path = os.path.relpath(os.path.join(root, filename), models_block_dir)
                full_model_path = os.path.join(models_block_dir, model_path)

                if full_model_path not in linked_model_paths:
                    print(f"Unlinked model file found: {model_path}")
                    src_path = full_model_path
                    dest_path = os.path.join(unlinked_models_dir, model_path)
                    dest_folder = os.path.dirname(dest_path)

                    if not os.path.exists(dest_folder):
                        os.makedirs(dest_folder)

                    # Move the file without asking for authorization
                    shutil.move(src_path, dest_path)
                    print(f"File moved successfully.")
                else:
                    print(f"Model file is linked: {model_path}")

    # Move unlinked texture files to unlinked_textures folder
    textures_block_dir = os.path.join(textures_dir, 'block')
    print(textures_block_dir)
    for root, _, files in os.walk(textures_block_dir):
        print(files)
        for filename in files:
            if filename.endswith('.png'):
                texture_path = os.path.relpath(os.path.join(root, filename), textures_block_dir)
                full_texture_path = os.path.join(textures_block_dir, texture_path)

                if full_texture_path not in linked_texture_paths:
                    print(f"Unlinked texture file found: {texture_path}")
                    src_path = full_texture_path
                    dest_path = os.path.join(unlinked_textures_dir, texture_path)
                    dest_folder = os.path.dirname(dest_path)

                    if not os.path.exists(dest_folder):
                        os.makedirs(dest_folder)

                    # Move the file without asking for authorization
                    shutil.move(src_path, dest_path)
                    print(f"File moved successfully.")
                else:
                    print(f"Texture file is linked: {texture_path}")


if __name__ == "__main__":
    main()
