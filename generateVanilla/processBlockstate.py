import json
import os
# import re

import generateVanilla
import processModel
import constants


# work on variant blockstates
def process_variants(variants, limit):
    for key, models in variants.items():
        if isinstance(models, list):
            model_count = 0
            for model in models[:]:
                if limit < 0 or model_count < limit:
                    processModel.process(model)
                else:
                    model.remove(model)
                model_count = model_count + 1
        else:
            processModel.process(models)


# work on multipart blockstates
def process_multipart(multipart, limit):
    for part in multipart:
        if isinstance(part["apply"], list):
            model_count = 0
            for model in part["apply"][:]:
                if limit < 0 or model_count < limit:
                    processModel.process(model)
                else:
                    part["apply"].remove(model)
                model_count = model_count + 1
        else:
            processModel.process(part["apply"])


def process(file):
    # load sodium blockstate file
    input_file = generateVanilla.input_path / constants.RELATIVE_BLOCKSTATE_PATH / file
    with open(input_file, 'r') as f:
        data = json.load(f)

    # check blockstate structure
    if "variants" in data:
        process_variants(data["variants"], generateVanilla.limit)
    elif "multipart" in data:
        process_multipart(data["multipart"], generateVanilla.limit)

    # write vanilla blockstate file
    output_file = generateVanilla.output_path / constants.RELATIVE_BLOCKSTATE_PATH / file
    os.makedirs(output_file.parent, exist_ok=True)
    with open(output_file, 'w') as file:
        if generateVanilla.compress:
            json.dump(data, file, separators=(',', ':'))
        else:
            json.dump(data, file, indent=4)
