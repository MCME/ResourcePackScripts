"""Reads an objmc carrier face back the way objmc_main.glsl does.

For each of the face's four corners: the header values, and the raw texels of
the position and UV the corner resolves to, and a digest of the texture the
shader samples. Two bakes that decode the same render the same.
"""

import hashlib
import math

MARKER = (12, 34, 56, 255)


def decode_face(image, uv):
    width, height = image.size
    px = image.load()
    corners = []
    for corner in range(4):
        # The client gives face vertex 0 (min u, min v), 1 (min u, max v),
        # 2 (max u, max v), 3 (max u, min v).
        u = uv[0] if corner in (0, 1) else uv[2]
        v = uv[1] if corner in (0, 3) else uv[3]
        x, y = int(u * width / 16), int(v * height / 16)
        r, g, b, a = px[x, y]
        offset_x, offset_y = r * 256 + g, b * 256 + a
        left, top = x - offset_x, y - offset_y
        t = [px[left + i, top] for i in range(16)]
        assert t[0] == MARKER, f"no header for corner {corner}"

        size_x = t[1][0] * 256 + t[1][1]
        size_y = t[1][2] * 256 + t[7][0]
        vertex_count = t[2][0] * 16777216 + t[2][1] * 65536 + t[2][2] * 256 + t[7][1]
        position_rows = t[5][0] * 256 + t[5][1]
        uv_rows = t[5][2] * 256 + t[7][2]
        max_lod = min(t[6][1], 4)
        texture_top = 2 + math.ceil(vertex_count * 0.25 / size_x)
        data_top = texture_top + size_y
        if t[8][0] == 2:
            data_top = texture_top
            texture_top = -(t[8][1] * 256 + t[8][2])
        elif max_lod > 0:
            block = 1 << max_lod
            texture_top = (texture_top + 2 * block - 1) // block * block
            data_top = (texture_top + size_y + block - 1) // block * block + block

        def at(row, i):
            return px[left + i % size_x, top + row + i // size_x]

        vertex = ((offset_y - 2) * size_x + offset_x) * 4 + corner
        index_rows = data_top + position_rows + uv_rows
        p, q = at(index_rows, vertex * 2), at(index_rows, vertex * 2 + 1)
        position = p[0] * 65536 + p[1] * 256 + p[2]
        texcoord = q[0] * 65536 + q[1] * 256 + q[2]
        texture = image.crop((left, top + texture_top, left + size_x, top + texture_top + size_y))
        corners.append((
            tuple(t[1:8]),
            tuple(at(data_top, position * 3 + k) for k in range(3)),
            tuple(at(data_top + position_rows, texcoord * 2 + k) for k in range(2)),
            hashlib.md5(texture.tobytes()).hexdigest(),
        ))
    return tuple(corners)


def decode_model(image, elements):
    return [
        decode_face(image, face["uv"])
        for element in elements
        for face in element["faces"].values()
        if face.get("texture") == "#0"
    ]
