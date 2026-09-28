import logging
from pathlib import Path

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


def split_namespaced(identifier: str, default_namespace=constants.VANILLA_NAMESPACE):
    """Splits a resource identifier into its namespace and path components"""

    if ":" in identifier:
        namespace, path = identifier.split(":", 1)
        return namespace, path
    return default_namespace, identifier


# Resolves a model identifier to a file path relative to a pack root, or None
# when the identifier names a built-in model and so has no file to resolve to.
def resolve_model_file(model_identifier):
    namespace, model_name = split_namespaced(model_identifier)
    if model_name.startswith(constants.BUILTIN_MODEL_PREFIX):
        return None
    return f"assets/{namespace}/models/{model_name}{constants.VANILLA_MODEL_EXTENSION}"


# Resolves a texture identifier to a file path relative to a pack root.
def resolve_texture_file(texture_identifier):
    namespace, texture_name = split_namespaced(texture_identifier)
    return f"assets/{namespace}/textures/{texture_name}{constants.TEXTURE_EXTENSION}"


def contained_path(root, relative):
    """`root / relative`, resolved - or None when that leads outside `root`.

    These paths are built from pack content, which is only text: a `..`
    segment, an absolute path or a symlink committed to the pack could point one
    anywhere on the machine running the conversion. Resolving follows all three,
    so comparing the result with the resolved root catches each of them. An
    absolute `relative` is checked as it is.
    """
    root = Path(root).resolve()
    path = (root / relative).resolve()
    return path if path.is_relative_to(root) else None


def warn_outside_pack(what, skipping):
    print(f"WARNING!!! {what} leads outside the pack - skipping {skipping}", flush=True)


def remove_tintindex(data):
    if "elements" in data:
        for element in data["elements"]:
            if "faces" in element:
                for face in element["faces"].values():
                    face.pop("tintindex", None)
