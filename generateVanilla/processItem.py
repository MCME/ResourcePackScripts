import json
import os

import constants
import processModel
import util

# Item model object types that contain a model identifier, and the field holding it
# https://minecraft.wiki/w/Items_model_definition#Items_model_types
MODEL_IDENTIFIER_FIELDS = {
    "model": "model",
    "special": "base",
}


# Yields (item model object, field) for every model file the definition names.
# Finds leaves wherever they appear rather than walking containers by type, so an
# unknown container cannot hide its models. Yields the field, not the identifier,
# so a converted model can be written back.
def model_identifier_fields(node):
    if isinstance(node, list):
        for item in node:
            yield from model_identifier_fields(item)
        return

    if not isinstance(node, dict):
        return

    _, node_type = util.split_namespaced(node.get("type", ""))
    field = MODEL_IDENTIFIER_FIELDS.get(node_type)
    if field is not None and isinstance(node.get(field), str):
        yield node, field

    for value in node.values():
        yield from model_identifier_fields(value)


# Works out where an item model definition should be read from
# override > resource pack > vanilla
def resolve_item_definition_file(input_path, vanilla_path, file):
    override_file = (
        input_path
        / constants.RELATIVE_VANILLA_OVERRIDES_PATH
        / constants.RELATIVE_ITEMS_PATH
        / file
    )
    resource_pack_file = input_path / constants.RELATIVE_ITEMS_PATH / file

    for candidate in (override_file, resource_pack_file):
        if candidate.exists():
            return candidate, False

    return vanilla_path / constants.RELATIVE_ITEMS_PATH / file, True


def write_item_definition_file(output_path, file, data, compress):
    output_file = output_path / constants.RELATIVE_ITEMS_PATH / file
    os.makedirs(output_file.parent, exist_ok=True)
    with open(output_file, "w") as f:
        if compress:
            json.dump(data, f, separators=(",", ":"))  # type: ignore
        else:
            json.dump(data, f, indent=4)  # type: ignore


def process(
    input_path,
    output_path,
    vanilla_path,
    item_file_name,
    compress,
    objmc_path,
    debug,
):
    input_file, from_vanilla = resolve_item_definition_file(
        input_path, vanilla_path, item_file_name
    )
    util.printDebug(f"Working on item file: {item_file_name}", debug)

    with open(input_file, "r") as f:
        data = json.load(f)

    for node, field in model_identifier_fields(data):
        model_entry = {"model": node[field]}
        processModel.process(
            input_path,
            output_path,
            vanilla_path,
            model_entry,
            objmc_path,
            compress,
            debug,
        )
        node[field] = model_entry["model"]

    if from_vanilla:
        # No need to write a vanilla item model definition
        return

    write_item_definition_file(output_path, item_file_name, data, compress)
