import os
import shutil


def printDebug(message, debug):
    if debug:
        print(message, flush=True)


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
