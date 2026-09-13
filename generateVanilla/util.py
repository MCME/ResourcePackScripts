import logging

import constants

logging.basicConfig(
    level=logging.DEBUG,  # Mindestlevel der Nachrichten
    format="%(asctime)s - %(levelname)s - %(message)s",  # Format der Nachrichten
    filename="debug.log",  # Log-File, in das geschrieben wird
    filemode="w",  # 'w' überschreibt das File, 'a' hängt an das File an
)


def printDebug(message, debug):
    if debug:
        print(message, flush=True)
        logging.info(message)


def split_namespaced(value, default_namespace=constants.VANILLA_NAMESPACE):
    """Split 'namespace:path' → (namespace, path). No ':' → (default_namespace, value)."""
    if ":" in value:
        namespace, path = value.split(":", 1)
        return namespace, path
    return default_namespace, value


def get_relative_model_path(namespaced_key):
    namespace = namespaced_key.split(":")[0]
    if namespace == constants.MCME_NAMESPACE:
        return constants.RELATIVE_SODIUM_MODELS_PATH
    else:
        return constants.RELATIVE_VANILLA_MODELS_PATH


def get_relative_texture_path(namespaced_key):
    namespace = namespaced_key.split(":")[0]
    if namespace == constants.MCME_NAMESPACE:
        return constants.RELATIVE_SODIUM_TEXTURES_PATH
    else:
        return constants.RELATIVE_VANILLA_TEXTURES_PATH


def remove_tintindex(data):
    if "elements" in data:
        for element in data["elements"]:
            if "faces" in element:
                for face in element["faces"].values():
                    face.pop("tintindex", None)
