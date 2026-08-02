import json
import os

import constants
import processModel
import util


# Processes a single model entry, which may be a singular model or a weighted list of models
# Uses the limit to cap the numbers of models for a singular entry
def process_model_entry(
    input_path, output_path, vanilla_path, entry, limit, objmc_path, compress, debug
):
    if not isinstance(entry, list):
        # Entry is a singular model
        processModel.process(
            input_path, output_path, vanilla_path, entry, objmc_path, compress, debug
        )
        return

    if limit >= 0:
        # **Mutating** the models list in place
        del entry[limit:]

    for model in entry:
        processModel.process(
            input_path, output_path, vanilla_path, model, objmc_path, compress, debug
        )


def model_entries(data):
    if "variants" in data:
        return data["variants"].values()
    if "multipart" in data:
        return (part["apply"] for part in data["multipart"])
    return ()


def process(
    input_path, output_path, vanilla_path, file, limit, compress, objmc_path, debug
):
    # TODO: Refactor the logic used to find the blockstate file

    # first check for blockstate file in vanilla override folder
    input_file = (
        input_path
        / constants.RELATIVE_VANILLA_OVERRIDES_PATH
        / constants.RELATIVE_BLOCKSTATE_PATH
        / file
    )
    is_vanilla_blockstate = False
    if not input_file.exists():
        # second check for blockstate file in resource pack
        input_file = input_path / constants.RELATIVE_BLOCKSTATE_PATH / file
        if not input_file.exists():
            # use vanilla blockstate file
            input_file = vanilla_path / constants.RELATIVE_BLOCKSTATE_PATH / file
            is_vanilla_blockstate = True
    util.printDebug(f"Working on blockstate file: {file}", debug)

    with open(input_file, "r") as f:
        data = json.load(f)

    for entry in model_entries(data):
        process_model_entry(
            input_path,
            output_path,
            vanilla_path,
            entry,
            limit,
            objmc_path,
            compress,
            debug,
        )

    # write vanilla blockstate file # FIXME: confusing comment
    if not is_vanilla_blockstate:
        output_file = output_path / constants.RELATIVE_BLOCKSTATE_PATH / file
        os.makedirs(output_file.parent, exist_ok=True)
        with open(output_file, "w") as file:
            if compress:
                json.dump(data, file, separators=(",", ":"))  # type: ignore
            else:
                json.dump(data, file, indent=4)  # type: ignore
