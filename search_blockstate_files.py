import json
import sys
from pathlib import Path


def load_json_file(filepath):
    try:
        with filepath.open('r') as file:
            return json.load(file)
    except json.JSONDecodeError as e:
        print(f"Fehler beim Laden der JSON-Datei {filepath}: {e}")
        return None


def find_model_entries(data, search_model, filepath):
    result = [('o', 0)]
    for key, value in data.get('variants', {}).items():
        # print(str(key)," ",str(value))
        if not isinstance(value, list):
            value = [value]
        for entry in value:
            # print(search_model)
            # print(entry.get('model'))
            if entry.get('model') == search_model:
                print("Found model in blockstate file.")
                # Die Einträge "x", "y", "z" extrahieren, falls vorhanden
                x = entry.get('x', 0)
                y = entry.get('y', 0)
                z = entry.get('z', 0)
                print(f'Gefunden in Datei {filepath}, {key}: x={x}, y={y}, z={z}')
                if x != 0:
                    if ('x', x) not in result:
                        result.extend(('x', x))
                        print("x: ",x)
                else:
                    if y != 0:
                        if ('y', y) not in result:
                            result.extend(('y', y))
                            print("y ",y)
                    else:
                        if z != 0:
                            if ('z', z) not in result:
                                result.extend(('z', z))
                                print("z: ",z)
                        else:
                            if ('o', 0) not in result:
                                result.extend(('o', 0))
                                print("o (should never occur!): ",0)
    # print(str(result))
    return result


def process_directory(directory, search_model):
    print("Searching blockstate files in: ", str(directory))
    #  directory = Path(directory)  # Verzeichnis in ein Path-Objekt umwandeln
    result = []
    for filepath in directory.rglob("*.json"):  # Alle JSON-Dateien rekursiv durchsuchen
        # print(f"Blockstate file: {filepath}")
        data = load_json_file(filepath)
        if data:
            for key, value in find_model_entries(data, search_model, filepath):
                if (key, value) not in result:
                    result.append((key, value))
    # print(str(result))
    return result


def main():
    if len(sys.argv) < 3:
        print("Verwendung: python script.py <directory> <search_model>")
        sys.exit(1)

    directory = sys.argv[1]
    search_model = sys.argv[2]

    directory_path = Path(directory)

    if not directory_path.is_dir():
        print(f"Das angegebene Verzeichnis {directory} existiert nicht.")
        sys.exit(1)

    process_directory(directory_path, search_model)


if __name__ == "__main__":
    main()
