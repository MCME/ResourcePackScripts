import json
import os
# import re

import processModel
import constants
import util


# work on variant blockstates
def process_variants(input_path, output_path, vanilla_path, variants, limit, objmc_path, compress, debug):
    for key, models in variants.items():
        if isinstance(models, list):
            model_count = 0
            for model in models[:]:
                if limit < 0 or model_count < limit:
                    processModel.process(input_path, output_path, vanilla_path, model, objmc_path, compress, debug)
                else:
                    models.remove(model)
                model_count = model_count + 1
        else:
            processModel.process(input_path, output_path, vanilla_path, models, objmc_path, compress, debug)


# work on multipart blockstates
def process_multipart(input_path, output_path, vanilla_path, multipart, limit, objmc_path, compress, debug):
    for part in multipart:
        if isinstance(part["apply"], list):
            model_count = 0
            for model in part["apply"][:]:
                if limit < 0 or model_count < limit:
                    processModel.process(input_path, output_path, vanilla_path, model, objmc_path, compress, debug)
                else:
                    part["apply"].remove(model)
                model_count = model_count + 1
        else:
            processModel.process(input_path, output_path, vanilla_path, part["apply"], objmc_path, compress, debug)


def process(input_path, output_path, vanilla_path, file, limit, compress, objmc_path, debug):
    # load sodium blockstate file
    util.printDebug(f"Working on blockstate file: {file}", debug)

    input_file = input_path / constants.RELATIVE_BLOCKSTATE_PATH / file
    if not input_file.exists():
        input_file = vanilla_path / constants.RELATIVE_BLOCKSTATE_PATH / file

    with open(input_file, 'r') as f:
        data = json.load(f)

    # check blockstate structure
    if "variants" in data:
        process_variants(input_path, output_path, vanilla_path, data["variants"], limit, objmc_path, compress, debug)
    elif "multipart" in data:
        process_multipart(input_path, output_path, vanilla_path, data["multipart"], limit, objmc_path, compress, debug)

    # write vanilla blockstate file
    output_file = output_path / constants.RELATIVE_BLOCKSTATE_PATH / file
    os.makedirs(output_file.parent, exist_ok=True)
    with open(output_file, 'w') as file:
        if compress:
            json.dump(data, file, separators=(',', ':'))
        else:
            json.dump(data, file, indent=4)
