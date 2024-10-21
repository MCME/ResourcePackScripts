import json
import sys
from pathlib import Path


# Funktion zum Laden der JSON-Daten aus einer Datei
def load_json_file(filepath):
    try:
        with filepath.open('r') as file:
            return json.load(file)
    except json.JSONDecodeError as e:
        print(f"Fehler beim Laden der JSON-Datei {filepath}: {e}")
        return None


# Funktion, um alle Einträge mit dem gesuchten Model zu finden
def find_model_entries(data, search_model, filepath):
    result = []
    for key, value in data.get('variants', {}).items():
        for entry in value:
            # Prüfen, ob das Model mit dem gesuchten Model übereinstimmt
            if entry.get('model') == search_model:
                # Die Einträge "x", "y", "z" extrahieren, falls vorhanden
                x = entry.get('x', 0)
                y = entry.get('y', 0)
                z = entry.get('z', 0)
                print(f'Gefunden in Datei {filepath}, {key}: x={x}, y={y}, z={z}')
                if x != 0:
                    if 'x' not in result:
                        result.extend(('x', x))
                else:
                    if y != 0:
                        if 'y' not in result:
                            result.extend(('y', y))
                    else:
                        if y != 0:
                            if 'z' not in result:
                                result.extend(('z', z))
                        else:
                            if 'o' not in result:
                                result.extend(('o', 0))

        return result

    # Funktion, um durch alle Dateien im Verzeichnis zu iterieren


def process_directory(directory, search_model):
    directory = Path(directory)  # Verzeichnis in ein Path-Objekt umwandeln
    for filepath in directory.rglob("*.json"):  # Alle JSON-Dateien rekursiv durchsuchen
        print(f"Verarbeite Datei: {filepath}")
        data = load_json_file(filepath)
        if data:
            return find_model_entries(data, search_model, filepath)


# Hauptfunktion, um das Verzeichnis und das Modell als Argument zu übergeben
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
