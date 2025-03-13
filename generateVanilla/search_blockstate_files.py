import json
import sys
from pathlib import Path


def load_json_file(filepath):
    try:
        with filepath.open('r') as file:
            return json.load(file)
    except json.JSONDecodeError as e:
        print(f"Error while loading JSON file {filepath}: {e}")
        return None


def find_model_entries(value, search_model):  # , filepath):
    rotations = [('o', 0)]
    model_found = False
    if not isinstance(value, list):
        value = [value]
    for entry in value:
        # print(str(value))
        # print(str(entry))
        # print(search_model)
        # print(entry.get('model'))
        if entry.get('model') == search_model:
            model_found = True
            # print("Found model in blockstate file.")

            # Die Einträge "x", "y", "z" extrahieren, falls vorhanden
            x = entry.get('x', 0)
            y = entry.get('y', 0)
            z = entry.get('z', 0)
            # print(f'Found in file {filepath}: x={x}, y={y}, z={z}')
            if x != 0:
                if ('x', x) not in rotations:
                    rotations.append(('x', x))
                    # print("x: ", x)
            else:
                if y != 0:
                    if ('y', y) not in rotations:
                        rotations.append(('y', y))
                        # print("y ", y)
                else:
                    if z != 0:
                        if ('z', z) not in rotations:
                            rotations.append(('z', z))
                            # print("z: ", z)
                    else:
                        if ('o', 0) not in rotations:
                            rotations.append(('o', 0))
                            # print("o (this should never occur!): ", 0)
    # print(str(result))
    return [rotations, model_found]


def get_models(data, search_model):  # , filepath):
    rotations = [('o', 0)]
    model_found = False
    if "variants" in data:
        for key, value in data.get('variants', {}).items():
            # print(str(key)," ",str(value))
            result = find_model_entries(value, search_model)  # , filepath)
            if result[1]:
                model_found = True
            for rotation in result[0]:
                if rotation not in rotations:
                    rotations.append(rotation)
    elif "multipart" in data:
        # print("found  Multipart data: ", data["multipart"])
        for entry in data["multipart"]:
            result = find_model_entries(entry["apply"], search_model)  # , filepath)
            if result[1]:
                model_found = True
            for rotation in result[0]:
                if rotation not in rotations:
                    rotations.append(rotation)
    return [rotations, model_found]


def process_directory(directory, search_model):
    # print("Searching blockstate files in: ", str(directory))
    #  directory = Path(directory)  # Verzeichnis in ein Path-Objekt umwandeln
    all_blockstate_files = []
    all_rotations = []
    for filepath in directory.rglob("*.json"):  # Alle JSON-Dateien rekursiv durchsuchen
        # print(f"Blockstate file: {filepath}")
        data = load_json_file(filepath)
        if data:
            blockstate_files_and_rotations = get_models(data, search_model)  # , filepath)
            rotations = blockstate_files_and_rotations[0]
            model_found = blockstate_files_and_rotations[1]
            for key, value in rotations:
                if (key, value) not in all_rotations:
                    all_rotations.append((key, value))
            if model_found:
                if filepath.name not in all_blockstate_files:
                    all_blockstate_files.append(filepath.name)
    # print(str(result))
    result = [all_rotations, all_blockstate_files]
    return result


def main():
    if len(sys.argv) < 3:
        print("Usage: python script.py <directory> <search_model>")
        sys.exit(1)

    directory = sys.argv[1]
    search_model = sys.argv[2]

    directory_path = Path(directory)

    if not directory_path.is_dir():
        print(f"Specified directory {directory} does not exist.")
        sys.exit(1)

    process_directory(directory_path, search_model)


if __name__ == "__main__":
    main()
