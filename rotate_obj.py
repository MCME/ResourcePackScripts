import math
import sys
import os


def rotate(vertex, axis, angle):
    """Rotiert einen Vertex oder eine Normale um die angegebene Achse um den gegebenen Winkel (in Grad)."""
    x, y, z = vertex
    rad = math.radians(angle)

    if axis == 'x':
        new_y = y * math.cos(rad) - z * math.sin(rad)
        new_z = y * math.sin(rad) + z * math.cos(rad)
        return x, new_y, new_z
    elif axis == 'y':
        new_x = x * math.cos(rad) + z * math.sin(rad)
        new_z = -x * math.sin(rad) + z * math.cos(rad)
        return new_x, y, new_z
    elif axis == 'z':
        new_x = x * math.cos(rad) - y * math.sin(rad)
        new_y = x * math.sin(rad) + y * math.cos(rad)
        return new_x, new_y, z
    else:
        raise ValueError("Ungültige Achse. Muss 'x', 'y' oder 'z' sein.")


def process_obj_line(line, axis, angle):
    """Verarbeitet eine Zeile aus einer .obj-Datei, dreht Vertices oder Normalen und gibt die aktualisierte Zeile
    zurück. """
    parts = line.split()
    x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
    rotated = rotate((x, y, z), axis, angle)

    return f"{parts[0]} {rotated[0]} {rotated[1]} {rotated[2]}\n"


def rotate_obj_file(input_file, axis, angle):
    """Liest eine .obj-Datei, rotiert die Vertices und Normalen um die angegebene Achse und den Winkel und speichert
    sie in einer neuen Datei. """
    # Bestimme den Namen der Ausgabedatei
    base_name, ext = os.path.splitext(input_file)
    output_file = f"{base_name}_{axis}_{angle}{ext}"

    with open(input_file, 'r') as file:
        lines = file.readlines()

    with open(output_file, 'w') as file:
        for line in lines:
            if line.startswith('v ') or line.startswith('vn '):  # Vertices und Normalen bearbeiten
                rotated_line = process_obj_line(line, axis, angle)
                file.write(rotated_line)
            else:
                # Alle anderen Zeilen unverändert lassen
                file.write(line)

    print(f"Datei gespeichert: {output_file}")


if __name__ == "__main__":
    # Überprüfen, ob die erforderlichen Argumente übergeben wurden
    if len(sys.argv) != 4:
        print("Verwendung: python3 rotate_obj.py <obj_datei> <achse> <winkel>")
        sys.exit(1)

    # Argumente aus der Kommandozeile lesen
    main_input_file = sys.argv[1]
    main_axis = sys.argv[2].lower()
    main_angle = int(sys.argv[3])

    # Überprüfen, ob der Winkel gültig ist (90, 180 oder 270)
    if main_angle not in [90, 180, 270]:
        print("Ungültiger Winkel. Muss 90, 180 oder 270 sein.")
        sys.exit(1)

    # Führe die Rotation durch
    rotate_obj_file(main_input_file, main_axis, main_angle)
