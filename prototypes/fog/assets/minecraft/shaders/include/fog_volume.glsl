// Volumes: clouds and smoke, drawn whole rather than block by block. Each
// is one block whose model is a tiny face in its middle, its texture's UV in
// one texel of block/volume: an alpha of 253, red 167, blue 92, and in green
// which kind of volume it is. The vertex shader (fog_volume_main.glsl)
// spreads that face over where the volume's box shows on screen, just in
// front of it, and the fragment shader (fog_block.glsl's volumeLook) traces
// each pixel's view through the box. Nothing in it is cut off by blocks'
// faces, and each pixel is worked out once for each volume it sees, however
// big the volume is.
//
// The game draws a block only while its chunk section is in view, so a
// volume whose block's section is just out of view isn't drawn, though some
// of it would show: at the screen's edges, big clouds can go before they
// leave it. Shared by the vertex and fragment shaders: no derivatives here.
// Its settings are in fog_block_config.glsl, imported first.

#define VOLUME_CLOUD 1               // a cloud: the unconnected grey glass pane
#define VOLUME_COLUMN 2              // a slice of the volcano's smoke column: light grey
#define VOLUME_COLUMN_TOP 3          // its top slice: magenta
#define VOLUME_CHIMNEY 4             // a chimney's smoke: brown

// A number, 0 to 1, for the block at block (in the world, mod 64) and salt.
float volumeRand(vec3 block, int salt) {
    uvec3 p = uvec3(ivec3(floor(block)) & 63);
    uint h = p.x * 73856093u ^ p.y * 19349663u ^ p.z * 83492791u ^ uint(salt) * 2654435761u;
    h ^= h >> 13;
    h *= 0x5bd1e995u;
    h ^= h >> 15;
    return float(h & 0xFFFFu) / 65535.0;
}

// Where a volume's box is, from its block's middle - block, in the world mod
// 64 - and how far it reaches from there each way, in blocks.
void volumeBox(int kind, vec3 block, out vec3 middle, out vec3 reach) {
    if (kind == VOLUME_CLOUD) {
        middle = vec3(0.0);
        reach = vec3(1.0, CLOUD_TALL, 1.0) * CLOUD_SIZE * mix(1.0 - CLOUD_VARY, 1.0 + CLOUD_VARY, volumeRand(block, 1));
    } else if (kind == VOLUME_CHIMNEY) {
        middle = vec3(0.0, CHIMNEY_HEIGHT * 0.5 - 0.5, 0.0);
        reach = vec3(CHIMNEY_WIDTH, CHIMNEY_HEIGHT * 0.5, CHIMNEY_WIDTH);
    } else {
        middle = vec3(0.0);
        reach = vec3(SMOKE_RADIUS * 1.3, float(SMOKE_SLICE) * 0.5, SMOKE_RADIUS * 1.3);
    }
}
