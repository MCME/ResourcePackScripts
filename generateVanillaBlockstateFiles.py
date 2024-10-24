import json
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
def process_variants(variants):
    for key, model in variants.items():
        if isinstance(model, list):
            for entry in model:
                update_model(entry)
        else:
            update_model(model)


# work on multipart blockstates
def process_multipart(multipart):
    for part in multipart:
        if isinstance(part["apply"], list):
            for entry in part["apply"]:
                update_model(entry)
        else:
            update_model(part["apply"])


# load JSON-file
def process_json(file_path, output_path):
    with open(file_path, 'r') as f:
        data = json.load(f)

    # check blockstate structure
    if "variants" in data:
        process_variants(data["variants"])
    elif "multipart" in data:
        process_multipart(data["multipart"])

    # write vanilla blockstate file
    with open(output_path, 'w') as f:
        json.dump(data, f, indent=4)


def convert_blockstate_files(blockstate_list, input_path, output_path):
    for blockstate_file in blockstate_list:
        process_json(input_path / Path("assets/minecraft/blockstates/", blockstate_file),
                     output_path / Path("assets/minecraft/blockstates/", blockstate_file))
