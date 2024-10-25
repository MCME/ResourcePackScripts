import json
import os
# import re
from pathlib import Path


# convert model entry
def update_model(entry):
    model_value = entry.get("model", "")
    # check if one key of "x", "y", oder "z" exists
    x = entry.pop("x", None)
    y = entry.pop("y", None)
    z = entry.pop("z", None)

    # input_file = str(input_path / file_path)
    # base_name, ext = os.path.splitext(input_file)
    # output_file = output_path / Path(f"{base_name}_{axis}_{angle}{ext}")

    # create vanilla model name
    if x is not None:
        model_value += f"_x_{x}"
    if y is not None:
        model_value += f"_y_{y}"
    if z is not None:
        model_value += f"_z_{z}"

    # Replace "mcme" with "minecraft"
    # model_value = re.sub(r'mcme', 'minecraft', model_value)

    # update model entry
    entry["model"] = model_value


# work on variant blockstates
def process_variants(variants, limit):
    for key, model in variants.items():
        if isinstance(model, list):
            model_count = 0
            for entry in model[:]:
                if limit < 0 or model_count < limit:
                    update_model(entry)
                else:
                    model.remove(entry)
                model_count = model_count + 1
        else:
            update_model(model)


# work on multipart blockstates
def process_multipart(multipart, limit):
    for part in multipart:
        if isinstance(part["apply"], list):
            model_count = 0
            for entry in part["apply"][:]:
                if limit < 0 or model_count < limit:
                    update_model(entry)
                else:
                    part["apply"].remove(entry)
                model_count = model_count + 1
        else:
            update_model(part["apply"])


# load JSON-file
def process_json(input_file, output_file, limit):
    with open(input_file, 'r') as file:
        data = json.load(file)

    # check blockstate structure
    if "variants" in data:
        process_variants(data["variants"], limit)
    elif "multipart" in data:
        process_multipart(data["multipart"], limit)

    # write vanilla blockstate file
    if output_file.parent:
        os.makedirs(output_file.parent, exist_ok=True)
    with open(output_file, 'w') as file:
        json.dump(data, file, indent=4)
        # json.dump(data, file, separators=(',', ':'))


def convert_blockstate_files(blockstate_list, input_path, output_path, limit):
    for blockstate_file in blockstate_list:
        process_json(input_path / Path("assets/minecraft/blockstates/", blockstate_file),
                     output_path / Path("assets/minecraft/blockstates/", blockstate_file), limit)
