// The volumes' vertex part (see fog_volume.glsl), imported into main() right
// after fire_eye_main.glsl, whose fireLayer it reads, as it reads objmc_main.
// glsl's uv (the texel the face's UV is in), uvHigh (which corner of it the
// vertex has) and isCustom. Shared by vanilla's terrain.vsh and Sodium's
// block_layer_opaque.vsh: Position is the vertex's section-local position,
// Pos its position relative to the camera, lavaWorld its position in the
// world mod 64, VOLUME_MODELVIEW the model-view matrix, set there.

volumeKind = 0;
volumeCentre = vec3(0.0);
volumeBlock = vec3(0.0);
if (isCustom == 0 && fireLayer < 0) {
    ivec4 volumeTexel = ivec4(texelFetch(Sampler0, uv, 0) * 255.0 + 0.5);
    if (volumeTexel.a == 253 && volumeTexel.r == 167 && volumeTexel.b == 92 && volumeTexel.g >= 1 && volumeTexel.g <= 4)
        volumeKind = volumeTexel.g;
}

// The face becomes a quad facing the camera, covering where the volume's
// box shows on screen, in front of the volume (see below for how far): so
// terrain in front of the volume hides it, terrain inside it doesn't. With the
// camera in or right by the box, it covers the whole view, just in front of
// the camera. Its corners are told apart by its texture coordinate, as the
// eye's are.
if (volumeKind > 0) {
    vec3 middle, reach;
    volumeCentre = floor(Position) + 0.5 + (Pos - Position);                  // camera-relative
    volumeBlock = floor(Position) + 0.5 + (lavaWorld - Position);             // in the world, mod 64
    volumeBox(volumeKind, volumeBlock, middle, reach);
    vec3 corners[8];
    float nearest = 1.0e9;
    for (int i = 0; i < 8; i++) {
        vec3 side = vec3(i & 1, (i >> 1) & 1, (i >> 2) & 1) * 2.0 - 1.0;
        corners[i] = (VOLUME_MODELVIEW * vec4(volumeCentre + middle + reach * side, 1.0)).xyz;
        nearest = min(nearest, -corners[i].z);
    }
    float depth = max(nearest, 0.3);
    // Volumes overlap: translucent blocks write their depth, so a volume
    // drawn before another - the game draws the farther first - must not be
    // in front of it, or it hides it, faint edges and all. So a cloud's
    // quad is as far in front of its middle as the biggest cloud reaches,
    // whatever its own size, and a column's slices all at one depth - in
    // front of where its axis is, level with the camera - so that their
    // quads lie in one plane.
    if (volumeKind == VOLUME_CLOUD) {
        depth = max(-(VOLUME_MODELVIEW * vec4(volumeCentre, 1.0)).z - CLOUD_SIZE * (1.0 + CLOUD_VARY) * 1.42, 0.3);
    } else if (volumeKind == VOLUME_COLUMN || volumeKind == VOLUME_COLUMN_TOP) {
        vec3 axis = (VOLUME_MODELVIEW * vec4(volumeCentre.x, 0.0, volumeCentre.z, 1.0)).xyz;
        depth = max(-axis.z - reach.x * 1.42, 0.3);
    }
    vec2 lo = vec2(1.0e9), hi = vec2(-1.0e9);
    if (nearest > 0.3) {
        for (int i = 0; i < 8; i++) {
            vec2 onPlane = corners[i].xy * depth / -corners[i].z;
            lo = min(lo, onPlane);
            hi = max(hi, onPlane);
        }
    } else {
        lo = vec2(-4.0 * depth);
        hi = vec2(4.0 * depth);
    }
    // corners 0-3 run (low u, low v), (low u, high v), (high u, high v),
    // (high u, low v): high v at the bottom keeps them anticlockwise on
    // screen, facing the camera
    vec3 corner = vec3(uvHigh.x ? hi.x : lo.x, uvHigh.y ? lo.y : hi.y, -depth);
    vec3 moved = (inverse(VOLUME_MODELVIEW) * vec4(corner, 1.0)).xyz;
    lavaWorld += moved - Pos;
    Pos = moved;
}
