// Lava: molten rock burning in layers under its surface, as the fire eye's
// ball burns in nested spheres (fire_eye.glsl) but slower, with a cooled
// crust drifting on still lava in rafts that glow through the cracks across
// them, and bubbles bursting on its open melt. Drawn per pixel over the
// lava's own faces - the fluid's, and the pack's models textured with it -
// fixed in the world: still lava stirs, flowing lava runs the way the game
// makes it flow, and falls stream down. Pixelated as a 16px texture is
// (LAVA_PIXEL); its settings are in lava_config.glsl. Needs fluid.glsl,
// which tells its faces from others (fluidKind) - see there.

#define LAVA_STILL FLUID_LAVA_STILL
#define LAVA_FLOWING FLUID_LAVA_FLOWING

// ---------------------------------------------------------------- its look

// The lava's heat as colour, as glowing rock has it: near black, through deep
// red and orange, to yellow only where it is hottest.
vec3 lavaShade(float x) {
    vec3 c = mix(vec3(0.035, 0.008, 0.0), vec3(0.4, 0.035, 0.0), smoothstep(0.0, 0.3, x));
    c = mix(c, vec3(0.8, 0.17, 0.01), smoothstep(0.25, 0.55, x));
    c = mix(c, vec3(1.0, 0.43, 0.05), smoothstep(0.5, 0.8, x));
    c = mix(c, vec3(1.0, 0.68, 0.24), smoothstep(0.78, 1.05, x));
    return mix(c, vec3(1.0, 0.88, 0.6), smoothstep(1.05, 1.4, x));
}

// How long a bubble takes to rise and pop, in seconds: each divides the
// day's 1200, so bubbles come back as the day's clock starts over.
const float LAVA_BUBBLE_TIMES[6] = float[6](5.0, 6.0, 8.0, 10.0, 12.0, 15.0);

// Bubbles on open melt at q (blocks, drifting with it): one in some of the
// cells of LAVA_BUBBLE_SPACING blocks at a time, each rising as a dark
// skinned dome with a hot rim, then bursting in a bright ring that spreads
// and fades. What they add to the heat there.
float lavaBubbles(vec2 q, float time, float pixel) {
    vec2 b = q / LAVA_BUBBLE_SPACING;
    ivec2 cell = ivec2(floor(b));
    ivec2 id = cell & (int(64.0 / LAVA_BUBBLE_SPACING) - 1);
    float period = LAVA_BUBBLE_TIMES[int(fluidRand(ivec4(id, 0, 670)) * 5.99)];
    float t = time / period + fluidRand(ivec4(id, 1, 670)) * 4.0;
    // which rise this is, of the day's: each comes up somewhere else, and
    // only some at all
    int rise = int(floor(t)) % int(1200.0 / period);
    float life = fract(t);
    if (fluidRand(ivec4(id, rise, 671)) > LAVA_BUBBLES) return 0.0;
    vec2 at = vec2(cell) + 0.3 + 0.4 * vec2(fluidRand(ivec4(id, rise, 672)), fluidRand(ivec4(id, rise, 673)));
    float d = length(b - at) * LAVA_BUBBLE_SPACING;
    float size = (0.12 + 0.18 * fluidRand(ivec4(id, rise, 674))) * min(LAVA_BUBBLE_SPACING * 0.5, 1.0);
    // smaller than a pixel, it isn't seen
    float seen = smoothstep(0.5, 1.5, size / pixel);
    if (life < 0.3) {
        float r = size * smoothstep(0.0, 0.3, life);
        float dome = 1.0 - smoothstep(r - LAVA_PIXEL, r, d);
        float rim = (1.0 - smoothstep(r, r + LAVA_PIXEL * 1.5, d)) - dome;
        return (-0.28 * dome * (1.0 - d / max(r, 1.0e-3)) + 0.3 * rim) * seen;
    }
    if (life < 0.42) {
        float burst = (life - 0.3) / 0.12;
        float r = size * (1.0 + 1.2 * burst);
        float ring = 1.0 - smoothstep(LAVA_PIXEL * 0.5, LAVA_PIXEL * 1.5, abs(d - r));
        float hole = 1.0 - smoothstep(r * 0.5, r * 0.8, d);
        return (0.55 * ring - 0.2 * hole) * (1.0 - burst) * seen;
    }
    return 0.0;
}

// The lava's colour at f, a face of kind, time seconds into the day.
vec3 lavaColor(int kind, FluidFrame f, float time) {
    vec3 n = fluidNormal(f);
    bool top = abs(n.y) > 0.6;
    // the face's own axes: x and z on top (and on flowing lava's slopes),
    // along it and up on its sides - always the world's own axes
    vec3 axisU = top ? vec3(1.0, 0.0, 0.0) : abs(n.x) > abs(n.z) ? vec3(0.0, 0.0, 1.0) : vec3(1.0, 0.0, 0.0);
    vec3 axisV = top ? vec3(0.0, 0.0, 1.0) : vec3(0.0, 1.0, 0.0);

    // pixelated: the face is cut into squares of LAVA_PIXEL blocks, each
    // traced once, through its middle
    vec2 s = vec2(dot(f.world, axisU), dot(f.world, axisV));
    vec2 snap = (floor(s / LAVA_PIXEL) + 0.5) * LAVA_PIXEL - s;
    vec3 shift = axisU * snap.x + axisV * snap.y;
    vec3 world = f.world + shift;
    vec3 ray = normalize(f.pos + shift);
    float pixel = max(max(length(f.dx), length(f.dy)), LAVA_PIXEL);

    // how it moves: flowing lava along its texture's flow, faster on top
    // than below; still lava stirred, each layer its own way
    vec3 v = fluidFlow(f);
    vec2 flow = vec2(dot(v, axisU), dot(v, axisV));
    bool flowing = kind == LAVA_FLOWING && dot(flow, flow) > 0.0;
    ivec2 way = flowing ? fluidWay(flow) : ivec2(0);
    int steps = top ? LAVA_FLOW_STEPS : LAVA_FALL_STEPS;
    mat2 along = fluidAlong(way);
    // flowing lava's patterns are drawn out a little along it
    vec2 stretch = flowing ? vec2(top ? 0.75 : 0.5, 1.0) : vec2(1.0);
    vec2 here = vec2(dot(world, axisU), dot(world, axisV));

    // the surface, drifting as its top layer does
    ivec2 drift = flowing ? way * steps : FLUID_STIR[0] * LAVA_CHURN;
    vec2 c = along * (here - vec2(drift) * FLUID_STEP * time);

    // ---- the crust, on still lava only: cooled rock floating on it in
    // shapeless rafts that drift with the surface and slowly change, cracked
    // across, the melt glowing up through the cracks and round their edges.
    // Worked out first: where it covers the melt whole, the melt isn't, and
    // where there is none of it, nor are its cracks and rock.
    bool still = kind == LAVA_STILL;
    float raft = 0.0, rim = 0.0, lip = 0.0, crack = 0.0, glow = 0.0;
    vec2 wc = vec2(0.0), jag = vec2(0.0);
    // far off, where its features shrink towards a pixel, the crust fades to
    // how much of the lava it covers, so it doesn't flicker
    float distant = smoothstep(0.15, 0.6, pixel / LAVA_PLATE);
    if (still) {
        // its shapes are warped by a field drifting another way, so they change
        vec2 m = here - vec2(FLUID_STIR[3]) * FLUID_STEP * time;
        vec2 crustCells = vec2(1.0 / LAVA_CRUST_SIZE);
        wc = c + fluidWarp(m, crustCells, pixel, 40) * 0.6 * LAVA_CRUST_SIZE
               + fluidWarp(c, crustCells * 4.0, pixel, 42) * 0.2 * LAVA_CRUST_SIZE;
        float field = fluidNoise(wc, crustCells, pixel, 44) * 0.6 + fluidNoise(wc, crustCells * 2.0, pixel, 45) * 0.28
                    + fluidNoise(wc, crustCells * 8.0, pixel, 46) * 0.12;
        // the field spreads about 0.13 round 0.5: this covers about LAVA_CRUST of it
        float edge = 0.5 + (0.5 - LAVA_CRUST) * 0.33;
        raft = smoothstep(edge, edge + 0.004, field);
        rim = 1.0 - smoothstep(edge, edge + 0.01, field);
        lip = (1.0 - smoothstep(edge + 0.01, edge + 0.03, field)) * (1.0 - rim);
    }
    bool crusted = raft > 0.0;
    if (crusted) {
        // cracks: the borders of two cell patterns, a coarse one and a finer
        // one, warped so they wander and jittered finely so they zigzag; open
        // only here and there, wider in some places than others
        jag = fluidWarp(wc, vec2(4.0), pixel, 47) * 0.22 + fluidWarp(wc, vec2(8.0), pixel, 49) * 0.12;
        for (int level = 0; level < 2; level++) {
            float size = LAVA_PLATE / float(1 << level);
            vec2 p = (wc + fluidWarp(wc, vec2(0.5 * float(1 << level)), pixel, 48 + level * 3) * 0.8 * size) / size
                   + jag * (2.0 / size);
            ivec2 cell = ivec2(floor(p));
            int mask = int(64.0 / size) - 1;
            float near = 1.0e9, second = 1.0e9;
            for (int k = 0; k < 9; k++) {
                ivec2 o = cell + ivec2(k % 3 - 1, k / 3 - 1);
                ivec2 id = o & mask;
                float d = length(p - vec2(o) - vec2(fluidRand(ivec4(id, level, 660)), fluidRand(ivec4(id, level + 2, 660))));
                second = d < near ? near : min(second, d);
                near = min(near, d);
            }
            float inside = (second - near) * 0.5 * size;
            float open = fluidNoise(wc, vec2(level == 0 ? 1.0 : 2.0), pixel, 50 + level);
            float width = LAVA_CRACK * (level == 0 ? 1.0 : 0.5) * smoothstep(level == 0 ? 0.3 : 0.62, level == 0 ? 0.8 : 0.85, open);
            if (width > 0.0) {
                crack = max(crack, 1.0 - smoothstep(width * 0.6, max(width, pixel), inside));
                glow = max(glow, 1.0 - smoothstep(width, width * 1.5 + LAVA_PIXEL, inside));
            }
        }
    }
    float crust = mix(raft * (1.0 - crack), raft * 0.85, distant);

    // basalt of a few kinds - grey, brown, rusty - by raft and patch, with
    // ropy ridges and pits, a lighter lip where it cooled first, and dull
    // red where the melt still heats it: by its edges and along the cracks
    float grain = 0.0;
    vec3 rock = vec3(0.0);
    if (crusted) {
        vec2 crustCells = vec2(1.0 / LAVA_CRUST_SIZE);
        grain = fluidNoise(c, vec2(16.0), pixel, 9);
        float clump = fluidNoise(c + 5.0, vec2(4.0), pixel, 10);
        float kindOf = fluidNoise(wc, crustCells * 2.0, pixel, 52);
        vec3 tone = mix(vec3(0.085, 0.078, 0.076), vec3(0.11, 0.078, 0.06), smoothstep(0.35, 0.65, kindOf));
        tone = mix(tone, vec3(0.15, 0.065, 0.045), smoothstep(0.6, 0.8, fluidNoise(wc, crustCells * 4.0, pixel, 53)) * 0.7);
        float ropes = 1.0 - abs(2.0 * fluidNoise(wc + jag * 2.0, vec2(2.0, 0.5), pixel, 54) - 1.0);
        rock = tone * (0.35 + 0.85 * grain + 0.5 * clump);
        rock *= 1.0 + 0.6 * smoothstep(0.8, 0.95, ropes) - 0.45 * smoothstep(0.75, 0.9, (1.0 - grain) * (1.0 - clump) * 1.6);
        rock = mix(rock, tone * 1.8, lip * 0.6);
        float warm = max(rim, glow);
        rock = mix(rock, lavaShade(0.2 + 0.12 * grain), warm * warm * 0.65);
        rock = mix(rock, lavaShade(0.45), smoothstep(0.9, 0.96, grain * (0.6 + 0.6 * clump)));
        rock = mix(rock, vec3(0.09, 0.05, 0.04), distant);
        if (crust >= 1.0) return rock;
    }

    // ---- the molten rock: turbulent swirls of heat in layers, deeper ones
    // seen further along the view ray, each warped and stirred its own way;
    // together they shift as the eye moves, as through a depth of melt
    float into = max(-dot(ray, n), 0.3);
    float heat = 0.0;
    float weight = 0.0;
    for (int i = 0; i < LAVA_LAYERS; i++) {
        vec3 at = world + ray * (float(i) * LAVA_LAYER_DEPTH / into);
        vec2 q = vec2(dot(at, axisU), dot(at, axisV));
        // each layer down a fifth slower, and pulled a little to one side
        ivec2 drift = flowing ? way * ((steps * (5 - i) + 2) / 5) + ivec2(-way.y, way.x) * ((i & 1) == 1 ? 1 : -1)
                              : FLUID_STIR[i] * LAVA_CHURN;
        q -= vec2(drift) * FLUID_STEP * time;
        q = flowing ? along * q : FLUID_TURN[i] * q;
        vec2 cells = FLUID_CELLS[i] * stretch;
        q += fluidWarp(q, cells * 0.5, pixel, i + 20) * 1.4 / cells;
        float a = fluidNoise(q, cells, pixel, i) * 0.6 + fluidNoise(q + 17.0, cells * 2.0, pixel, i + 8) * 0.25
                + fluidNoise(q + 31.0, cells * 4.0, pixel, i + 12) * 0.15;
        float w = 1.0 / (1.0 + 0.5 * float(i));
        heat += a * w;
        weight += w;
    }
    heat = (heat / weight - 0.5) * 1.9;

    // ---- finer things on it, so not all of it is the same size of swirl:
    // broad hotter and cooler stretches, a few thin threads of darker,
    // cooling skin and of brighter melt, drawn out by the stirring; and on
    // still lava, bubbles
    heat += (fluidNoise(c, vec2(0.125) * stretch, pixel, 60) - 0.5) * 0.5;
    vec2 tq = c + fluidWarp(c, vec2(0.5) * stretch, pixel, 61) * 2.5;
    float threads = 1.0 - abs(2.0 * fluidNoise(tq, vec2(1.0, 0.5) * stretch, pixel, 63) - 1.0);
    float where = smoothstep(0.55, 0.7, fluidNoise(c, vec2(0.25), pixel, 64));
    heat -= smoothstep(0.9, 0.98, threads) * where * (top ? 0.25 : 0.0);
    float sparks = 1.0 - abs(2.0 * fluidNoise(tq + 23.0, vec2(2.0, 1.0) * stretch, pixel, 65) - 1.0);
    heat += smoothstep(0.95, 0.99, sparks) * (1.0 - where) * smoothstep(0.5, 0.65, fluidNoise(c, vec2(0.25), pixel, 66)) * 0.35;
    if (kind == LAVA_STILL && top) heat += lavaBubbles(c, time, pixel);
    vec3 molten = lavaShade(0.62 + heat * LAVA_HEAT);
    if (!crusted) return molten;
    // cracks show the melt a little cooler than open lava
    vec3 melt = mix(molten, lavaShade(0.45 + heat * 0.8), raft * crack * 0.5);
    return mix(melt, rock, crust);
}
