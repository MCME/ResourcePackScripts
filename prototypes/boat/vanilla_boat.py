"""The vanilla boat's faces as Minecraft 26.2 builds and draws them (BoatModel,
ModelPart$Cube, ModelPart$Polygon, AbstractBoatRenderer), in the boat's own
frame: after the renderer's scale(-1, -1, 1) and 90 degree turn, before its
yaw - so that the world's is  entity + (0, 0.375, 0) + rotY(180 - yaw) * p."""
import numpy as np

TEX = (128, 64)

# part: (texOffs, box min, box size, pose offset, pose rotation x y z)
HULL = {
    "bottom": ((0, 0), (-14, -9, -3), (28, 16, 3), (0, 3, 1), (np.pi / 2, 0, 0)),
    "back": ((0, 19), (-13, -7, -1), (18, 6, 2), (-15, 4, 4), (0, 3 * np.pi / 2, 0)),
    "front": ((0, 27), (-8, -7, -1), (16, 6, 2), (15, 4, 0), (0, np.pi / 2, 0)),
    "right": ((0, 35), (-14, -7, -1), (28, 6, 2), (0, 4, -9), (0, np.pi, 0)),
    "left": ((0, 43), (-14, -7, -1), (28, 6, 2), (0, 4, 9), (0, 0, 0)),
}
# the paddles, only for their texture coordinates (they swing)
PADDLES = {
    "left_paddle_a": ((62, 0), (-1, 0, -5), (2, 2, 18)),
    "left_paddle_b": ((62, 0), (-1.001, -3, 8), (1, 6, 7)),
    "right_paddle_a": ((62, 20), (-1, 0, -5), (2, 2, 18)),
    "right_paddle_b": ((62, 20), (0.001, -3, 8), (1, 6, 7)),
}
DIRS = {"down": (0, -1, 0), "up": (0, 1, 0), "west": (-1, 0, 0), "north": (0, 0, -1), "east": (1, 0, 0), "south": (0, 0, 1)}


def rot_x(a):
    c, s = np.cos(a), np.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def rot_y(a):
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def rot_z(a):
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


# the renderer's fixed part, after its yaw: scale(-1, -1, 1), then rotY(90)
FIXED = np.diag([-1.0, -1.0, 1.0]) @ rot_y(np.pi / 2)


def cube_faces(tex, mn, size):
    """ModelPart$Cube: each face's 4 corners (pixels) and texture coordinates (pixels), in drawing order."""
    x0, y0, z0 = mn
    w, h, d = size
    x1, y1, z1 = x0 + w, y0 + h, z0 + d
    v = {19: (x0, y0, z0), 20: (x1, y0, z0), 21: (x1, y1, z0), 22: (x0, y1, z0),
         23: (x0, y0, z1), 24: (x1, y0, z1), 25: (x1, y1, z1), 26: (x0, y1, z1)}
    u_, v_ = tex
    U = {27: u_, 28: u_ + d, 29: u_ + d + w, 30: u_ + d + w + w, 31: u_ + d + w + d, 32: u_ + d + w + d + w}
    V = {33: v_, 34: v_ + d, 35: v_ + d + h}
    faces = {
        "down": ((24, 23, 19, 20), (28, 33, 29, 34)),
        "up": ((21, 22, 26, 25), (29, 34, 30, 33)),
        "west": ((19, 23, 26, 22), (27, 34, 28, 35)),
        "north": ((20, 19, 22, 21), (28, 34, 29, 35)),
        "east": ((24, 20, 21, 25), (29, 34, 31, 35)),
        "south": ((23, 24, 25, 26), (31, 34, 32, 35)),
    }
    out = []
    for name, (verts, (u1, v1, u2, v2)) in faces.items():
        # ModelPart$Polygon: corner 0 (u2, v1), 1 (u1, v1), 2 (u1, v2), 3 (u2, v2)
        uvs = [(U[u2], V[v1]), (U[u1], V[v1]), (U[u1], V[v2]), (U[u2], V[v2])]
        out.append((name, [np.array(v[i], float) for i in verts], uvs))
    return out


def hull():
    """Every hull face: (part, face, corners in the boat's frame (blocks), uv (pixels), normal)."""
    faces = []
    for part, (tex, mn, size, off, (rx, ry, rz)) in HULL.items():
        m = FIXED @ rot_z(rz) @ rot_y(ry) @ rot_x(rx)
        t = FIXED @ (np.array(off, float) / 16.0)
        for name, corners, uvs in cube_faces(tex, mn, size):
            pts = [t + m @ (c / 16.0) for c in corners]
            n = m @ np.array(DIRS[name], float)
            faces.append((part, name, pts, uvs, n))
    return faces


def paddle_keys():
    keys = []
    for part, (tex, mn, size) in PADDLES.items():
        for name, corners, uvs in cube_faces(tex, mn, size):
            keys += [(uv[0], uv[1], k) for k, uv in enumerate(uvs)]
    return keys


if __name__ == "__main__":
    fs = hull()
    allp = np.array([p for f in fs for p in f[2]])
    print("hull extent min", allp.min(0).round(3), "max", allp.max(0).round(3))
    for part, name, pts, uvs, n in fs:
        print(f"{part:7s} {name:6s} n={n.round(2)} centre={np.mean(pts, 0).round(3)} uv={uvs}")
