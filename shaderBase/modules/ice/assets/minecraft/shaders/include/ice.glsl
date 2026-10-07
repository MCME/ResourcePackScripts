// Ice: see-through, with what is frozen into it - big straight cracks,
// finer ones between, wandering fractures, a few trapped bubbles and
// clouding, in layers, the deeper fainter and bluer - faint scratches on its
// surface, and frost where it meets other blocks, glinting now and then.
// Drawn per pixel over the faces of what shows block/ice, fixed in the
// world, the same from wherever it is seen, so nothing in it shifts or
// flickers as the eye moves; no reflections, as nothing else in the world
// has them. Pixelated as a 16px texture is (ICE_PIXEL); its cracks never
// thinner than a pixel on screen, so they hold far off. Its settings are in
// ice_config.glsl. Needs fluid.glsl, which tells its faces from others
// (fluidKind), and water.glsl, whose shores give its frost: the game shades
// the corners of a block's faces that other blocks crowd, with smooth
// lighting, in vanilla as with Sodium - see there.

#define ICE FLUID_ICE

// What the ice looks like at a fragment, for its shader to light.
struct IceLook {
    vec3 color;
    float alpha;
    float frost;    // how much of it is frost, which the shade of what crowds it doesn't dim
};

// The borders between cells about size blocks across, warped by bend (in
// cells) and jag (in blocks): 1 within width blocks of one. salt picks the
// pattern.
float iceBorder(vec2 q, float size, float bend, float jag, float width, int salt) {
    vec2 p = (q + fluidWarp(q, vec2(0.5 / size), 0.0, salt + 300) * bend * size
              + fluidWarp(q, vec2(8.0), 0.0, salt + 310) * jag) / size;
    ivec2 cell = ivec2(floor(p));
    int mask = int(64.0 / size) - 1;
    float near = 1.0e9, second = 1.0e9;
    for (int k = 0; k < 9; k++) {
        ivec2 o = cell + ivec2(k % 3 - 1, k / 3 - 1);
        ivec2 id = o & mask;
        float d = length(p - vec2(o) - vec2(fluidRand(ivec4(id, salt, 320)), fluidRand(ivec4(id, salt, 321))));
        second = d < near ? near : min(second, d);
        near = min(near, d);
    }
    return 1.0 - step(width, (second - near) * 0.5 * size);
}

// A trapped bubble at q: in some cells of a quarter block, a pixel or two
// across.
float iceBubble(vec2 q, int salt) {
    vec2 b = q * 4.0;
    ivec2 cell = ivec2(floor(b));
    ivec2 id = cell & 255;
    if (fluidRand(ivec4(id, salt, 340)) > ICE_BUBBLES) return 0.0;
    vec2 at = vec2(cell) + 0.3 + 0.4 * vec2(fluidRand(ivec4(id, salt, 341)), fluidRand(ivec4(id, salt, 342)));
    float r = (0.06 + 0.05 * fluidRand(ivec4(id, salt, 343))) * 4.0;
    return 1.0 - step(r, length(b - at));
}

// The ice's look at f, time seconds into the day; shore from water.glsl's
// waterShore.
IceLook iceLook(FluidFrame f, float time, WaterShore shore) {
    vec3 n = fluidNormal(f);
    bool top = abs(n.y) > 0.6;
    vec3 axisU = top ? vec3(1.0, 0.0, 0.0) : abs(n.x) > abs(n.z) ? vec3(0.0, 0.0, 1.0) : vec3(1.0, 0.0, 0.0);
    vec3 axisV = top ? vec3(0.0, 0.0, 1.0) : vec3(0.0, 1.0, 0.0);

    // pixelated: the face is cut into squares of ICE_PIXEL blocks
    vec2 s = vec2(dot(f.world, axisU), dot(f.world, axisV));
    vec2 snap = (floor(s / ICE_PIXEL) + 0.5) * ICE_PIXEL - s;
    vec3 shift = axisU * snap.x + axisV * snap.y;
    vec2 here = s + snap;
    float pixel = max(max(length(f.dx), length(f.dy)), ICE_PIXEL);
    // lines a pixel wide, on screen at least
    float width = 0.6 * pixel;

    // ---- what is frozen into it, layer by layer, each fainter and bluer
    // than the one above and dimmed by what lies over it
    IceLook look;
    vec3 color = vec3(0.0);
    float through = 1.0;
    float solid = 0.0;
    for (int i = 0; i < ICE_LAYERS; i++) {
        float deep = (float(i) + 0.5) / float(ICE_LAYERS);
        vec2 q = FLUID_TURN[i] * here;
        float cloud = fluidNoise(q, vec2(1.0), pixel, i + 350) * 0.6 + fluidNoise(q + 5.0, vec2(2.0), pixel, i + 360) * 0.4;
        cloud = smoothstep(0.35, 0.8, cloud) * ICE_CLOUD;
        float lines = 0.0;
        if (i == 0) lines = iceBorder(here, ICE_CRACK_SIZE, 0.25, 0.05, width, 0) * ICE_CRACKS;
        if (i == 1) lines = iceBorder(here, ICE_FRACTURE_SIZE, 1.2, 0.1, width, 2) * smoothstep(0.35, 0.6, fluidNoise(here, vec2(1.0), pixel, 332)) * ICE_FRACTURES;
        if (i == 2) lines = iceBorder(here, ICE_CRACK_SIZE * 0.5, 0.25, 0.05, width, 1)
                          * step(1.0 - ICE_FINE_CRACKS, fluidNoise(here, vec2(0.5), pixel, 330)) * ICE_CRACKS * 0.6;
        if (i == 3) lines = iceBorder(here + 17.0, ICE_FRACTURE_SIZE, 1.2, 0.1, width, 3) * smoothstep(0.4, 0.65, fluidNoise(here, vec2(1.0), pixel, 333)) * ICE_FRACTURES * 0.7;
        float bubble = i > 0 ? iceBubble(q, i) * (1.0 - smoothstep(1.5, 3.0, pixel / ICE_PIXEL)) : 0.0;
        vec3 layer = mix(ICE_SURFACE, ICE_DEEP, deep) * (0.75 + 0.5 * cloud) + vec3(0.95, 0.98, 1.0) * (lines + bubble * 0.4);
        float share = 1.0 / float(ICE_LAYERS) + cloud * 0.4;
        color += layer * share * through;
        solid = max(solid, max(lines, bubble * 0.6) * (1.0 - 0.5 * deep));
        through *= 1.0 - min(share, 0.9);
        solid = max(solid, cloud * 0.5 * (1.0 - deep));
    }
    color += ICE_DEEP * through;

    // ---- its surface: faint scratches
    float scratches = 1.0 - abs(2.0 * fluidNoise(here + fluidWarp(here, vec2(2.0), 0.0, 370) * 0.3, vec2(8.0, 1.0), pixel, 372) - 1.0);
    color += vec3(0.06) * smoothstep(0.92, 0.98, scratches);

    // ---- frost where other blocks crowd it, its edge ragged, a few of its
    // pixels glinting in turn
    float away = waterAway(shore, f, shift);
    float ragged = fluidNoise(here, vec2(4.0), pixel, 380) * 0.6 + fluidNoise(here, vec2(16.0), pixel, 381) * 0.4;
    float frost = 1.0 - smoothstep(ICE_FROST * (0.5 + ragged) - ICE_PIXEL, ICE_FROST * (0.5 + ragged), away);
    float glint = fluidRand(ivec4(ivec2(floor(here / ICE_PIXEL)) & 1023, 0, 390));
    // (each glints 60 times a day, so all comes round as the day's clock does)
    float twinkle = smoothstep(0.9, 1.0, sin(time * (6.2831853 * 60.0 / 1200.0) + glint * 6.2831853 * 7.0));
    color = mix(color, ICE_FROST_COLOR * (0.85 + 0.25 * ragged), frost);
    color += vec3(0.5) * frost * step(1.0 - ICE_SPARKLE, glint) * twinkle;

    look.color = color;
    look.alpha = mix(ICE_ALPHA, 0.95, max(solid, frost));
    look.frost = frost;
    return look;
}
