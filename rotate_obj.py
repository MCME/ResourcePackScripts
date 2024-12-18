import math
import sys
import os
from pathlib import Path


def rotate(vertex, axis, angle):
    """Rotates a vertex or a normal."""
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
        raise ValueError("Invalid axis. Needs to be 'x', 'y' or 'z'.")


def process_obj_line(line, axis, angle):
    """Rotates all data of a single line."""
    parts = line.split()
    x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
    rotated = rotate((x, y, z), axis, angle)

    return f"{parts[0]} {rotated[0]} {rotated[1]} {rotated[2]}\n"


def rotate_obj_file(input_path, output_path, file_path, axis, angle):
    """Rotates all vertices and normals of a .obj file."""
    input_file = str(input_path / file_path)
    base_name, ext = os.path.splitext(input_file)
    output_file = output_path / Path(f"{base_name}_{axis}_{angle}{ext}")

    with open(input_file, 'r') as file:
        lines = file.readlines()

    with open(output_file, 'w') as file:
        for line in lines:
            if line.startswith('v ') or line.startswith('vn '):  # Vertices und Normalen bearbeiten
                rotated_line = process_obj_line(line, axis, angle)
                file.write(rotated_line)
            else:
                # don't change other lines
                file.write(line)

    # print(f"File saved: {output_file}")


if __name__ == "__main__":
    # check arguments
    if len(sys.argv) != 4:
        print("Usage: python3 rotate_obj.py <obj_file> <axis> <angle>")
        sys.exit(1)

    # read arguments from command line
    main_input_file = Path(sys.argv[1])
    main_axis = sys.argv[2].lower()
    main_angle = int(sys.argv[3])

    if not main_input_file.is_absolute():
        main_input_file = Path.cwd() / main_input_file
    # check angle (90, 180 oder 270)
    if main_angle not in [90, 180, 270]:
        print("Invalid angle. Needs to be 90, 180 oder 270.")
        sys.exit(1)

    # do rotation
    rotate_obj_file(main_input_file.parent, main_input_file.parent, Path(main_input_file.name), main_axis, main_angle)
