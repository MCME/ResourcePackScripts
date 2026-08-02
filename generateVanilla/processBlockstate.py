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


# Works out where a blockstate file should be read from
# override > resource pack > vanilla
def resolve_blockstate_file(input_path, vanilla_path, file):
    override_file = (
        input_path
        / constants.RELATIVE_VANILLA_OVERRIDES_PATH
        / constants.RELATIVE_BLOCKSTATE_PATH
        / file
    )
    resource_pack_file = input_path / constants.RELATIVE_BLOCKSTATE_PATH / file

    for candidate in (override_file, resource_pack_file):
        if candidate.exists():
            return candidate, False

    return vanilla_path / constants.RELATIVE_BLOCKSTATE_PATH / file, True


def write_blockstate_file(output_path, file, data, compress):
    output_file = output_path / constants.RELATIVE_BLOCKSTATE_PATH / file
    os.makedirs(output_file.parent, exist_ok=True)
    with open(output_file, "w") as f:
        if compress:
            json.dump(data, f, separators=(",", ":"))  # type: ignore
        else:
            json.dump(data, f, indent=4)  # type: ignore


def process(
    input_path, output_path, vanilla_path, file, limit, compress, objmc_path, debug
):
    input_file, from_vanilla = resolve_blockstate_file(input_path, vanilla_path, file)
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

    if from_vanilla:
        # No need to write a vanilla blockstate file
        return

    write_blockstate_file(output_path, file, data, compress)
