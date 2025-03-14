import os
import shutil
import constants
import logging


logging.basicConfig(
    level=logging.DEBUG,  # Mindestlevel der Nachrichten
    format='%(asctime)s - %(levelname)s - %(message)s',  # Format der Nachrichten
    filename='debug.log',  # Log-File, in das geschrieben wird
    filemode='w'  # 'w' überschreibt das File, 'a' hängt an das File an
)


def printDebug(message, debug):
    if debug:
        print(message, flush=True)
        logging.info(message)


def copy_folder(source, destination):
    if os.path.exists(source):
        if not os.path.exists(destination):
            os.makedirs(destination)
        for item in os.listdir(source):
            source_path = os.path.join(source, item)
            destination_path = os.path.join(destination, item)
            if os.path.isdir(source_path):
                copy_folder(source_path, destination_path)  # Rekursion für Unterordner
            else:
                shutil.copy2(source_path, destination_path)  # Kopiert Dateien
    else:
        print("copy_folder: Expected source not found: "+str(source))


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
