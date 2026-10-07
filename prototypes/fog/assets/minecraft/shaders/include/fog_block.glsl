// The fog block: a block of mist - the unconnected purple glass pane - drawn on its
// faces as how much mist the view passes through inside it: from where the
// view ray enters the block to where it leaves it, the mist along the way
// summed from drifting, slowly changing wisps, thinner towards its top. So it
// is soft at its edges, where the view only grazes it, and blocks of it side
// by side and stacked add up into one fog, every face of each drawn (its
// model has no cull faces). It drifts from the west, and thins out round the
// camera, so that one can walk in it. Lit by the light alone - no shading of
// its faces, which would show them - and tinted with the sky's colour.
// Pixelated as a 16px texture is (FOG_PIXEL); its settings are in
// fog_block_config.glsl. Needs fluid.glsl, which tells its faces from others
// (fluidKind): block/fog is signed - see there.
//
// The spray block - the unconnected light blue glass pane, block/spray - is
// drawn the same way: whiter mist, as where a waterfall comes down, in thin
// curling strands swept every way by a turbulent flow, grainy as the mist
// texture is, its grains streaming along with it.
//
// Clouds and smoke are volumes, drawn whole: see fog_volume.glsl, imported
// before this, and volumeLook below.

#define FOG_BLOCK FLUID_FOG
#define SPRAY_BLOCK FLUID_SPRAY

// How thick the mist is at p (blocks), time seconds into the day; local its
// place in its block.
float fogDensity(vec3 p, vec3 local, float time) {
    // east and a little south, the finer wisps slower and turning against it
    vec3 wind = vec3(ivec3(FOG_DRIFT, 0, FOG_DRIFT / 3)) * FLUID_STEP * time;
    vec3 wind2 = vec3(ivec3(FOG_DRIFT / 2, 0, -FOG_CHURN)) * FLUID_STEP * time;
    float n = fluidNoise3(p - wind, 1.0 / FOG_WISP, 800) * 0.65 + fluidNoise3(p - wind2, 2.0 / FOG_WISP, 810) * 0.35;
    float wisps = smoothstep(FOG_PATCHY - 0.15, FOG_PATCHY + 0.25, n);
    return wisps * (1.0 - FOG_SETTLE * local.y) * FOG_DENSITY;
}

// The fog's colour - over the light - and opacity at f, time seconds into
// the day; sky the sky's colour.
vec4 fogLook(FluidFrame f, float time, vec3 sky) {
    vec3 n = fluidNormal(f);
    bool top = abs(n.y) > 0.6;
    vec3 axisU = top ? vec3(1.0, 0.0, 0.0) : abs(n.x) > abs(n.z) ? vec3(0.0, 0.0, 1.0) : vec3(1.0, 0.0, 0.0);
    vec3 axisV = top ? vec3(0.0, 0.0, 1.0) : vec3(0.0, 1.0, 0.0);

    // pixelated: the face is cut into squares of FOG_PIXEL blocks, each
    // traced once, through its middle
    vec2 s = vec2(dot(f.world, axisU), dot(f.world, axisV));
    vec2 snap = (floor(s / FOG_PIXEL) + 0.5) * FOG_PIXEL - s;
    vec3 shift = axisU * snap.x + axisV * snap.y;
    vec3 entry = f.world + shift;
    vec3 ray = normalize(f.pos + shift);

    // the block it enters - behind the face - and how far the ray goes in it
    vec3 cell = floor(entry - n * 0.001);
    vec3 local = clamp(entry - cell, 0.0, 1.0);
    vec3 exits = vec3(ray.x > 0.0 ? (1.0 - local.x) / ray.x : ray.x < 0.0 ? -local.x / ray.x : 1.0e9,
                      ray.y > 0.0 ? (1.0 - local.y) / ray.y : ray.y < 0.0 ? -local.y / ray.y : 1.0e9,
                      ray.z > 0.0 ? (1.0 - local.z) / ray.z : ray.z < 0.0 ? -local.z / ray.z : 1.0e9);
    float length_ = min(exits.x, min(exits.y, exits.z));

    // the mist along it, a few looks spread over the way
    float depth = 0.0;
    for (int i = 0; i < FOG_SAMPLES; i++) {
        float t = (float(i) + 0.5) / float(FOG_SAMPLES) * length_;
        depth += fogDensity(entry + ray * t, clamp(local + ray * t, 0.0, 1.0), time);
    }
    depth *= length_ / float(FOG_SAMPLES);
    float alpha = (1.0 - exp(-depth)) * FOG_MOST;
    // thinning out round the camera
    alpha *= smoothstep(FOG_CLEAR * 0.3, FOG_CLEAR, length(f.pos));
    return vec4(mix(FOG_COLOR, sky, FOG_TINT), alpha);
}

// A turbulent flow's push at p, time seconds into the day: three fields,
// each drifting its own way, warping the place they are read at - so the
// push swirls, changes, and goes every way. In blocks; strength its size.
vec3 sprayFlow(vec3 p, float time, float strength) {
    // (whole steps of 64 blocks a day each way, so it is as it was when the
    // day's clock starts over)
    float step_ = float(SPRAY_SWIRL) * FLUID_STEP * time;
    vec3 a = p - vec3(5.0, 3.0, -4.0) * step_;
    vec3 b = p - vec3(-4.0, 5.0, 3.0) * step_;
    vec3 c = p - vec3(3.0, -4.0, 5.0) * step_;
    return (vec3(fluidNoise3(a, 0.5, 820), fluidNoise3(b, 0.5, 821), fluidNoise3(c, 0.5, 822)) - 0.5) * strength;
}

// How the spray's grains stream: each of three layers of them its own way,
// in whole steps of SPRAY_SWIRL's.
const vec3 SPRAY_STREAMS[3] = vec3[3](vec3(5.0, 3.0, -4.0), vec3(-4.0, -1.0, 5.0), vec3(-2.0, 4.0, -5.0));

// The spray's strands at p (blocks), time seconds into the day: thin and
// curling, swept about by the turbulent flow and changing as they go; 0 to 1.
float sprayStrands(vec3 p, float time) {
    float step_ = float(SPRAY_SWIRL) * FLUID_STEP * time;
    vec3 q = p + sprayFlow(p, time, 2.0 * SPRAY_CURL);
    q += sprayFlow(q * 2.0 + 3.0, time * 2.0, 0.5 * SPRAY_CURL);
    float n = fluidNoise3(q - vec3(2.0, 3.0, -1.0) * step_, 1.0 / SPRAY_CURL, 830);
    float strand = smoothstep(1.0 - SPRAY_STRAND, 1.0, 1.0 - abs(2.0 * n - 1.0));
    return strand * smoothstep(0.25, 0.65, fluidNoise3(q + 11.0 - vec3(-1.0, 2.0, 2.0) * step_, 0.5 / SPRAY_CURL, 831));
}

// The spray's colour - over the light - and opacity at f, time seconds into
// the day.
vec4 sprayLook(FluidFrame f, float time) {
    vec3 n = fluidNormal(f);
    bool top = abs(n.y) > 0.6;
    vec3 axisU = top ? vec3(1.0, 0.0, 0.0) : abs(n.x) > abs(n.z) ? vec3(0.0, 0.0, 1.0) : vec3(1.0, 0.0, 0.0);
    vec3 axisV = top ? vec3(0.0, 0.0, 1.0) : vec3(0.0, 1.0, 0.0);
    vec2 s = vec2(dot(f.world, axisU), dot(f.world, axisV));
    vec2 snap = (floor(s / FOG_PIXEL) + 0.5) * FOG_PIXEL - s;
    vec3 shift = axisU * snap.x + axisV * snap.y;
    vec3 entry = f.world + shift;
    vec3 ray = normalize(f.pos + shift);
    vec3 cell = floor(entry - n * 0.001);
    vec3 local = clamp(entry - cell, 0.0, 1.0);
    vec3 exits = vec3(ray.x > 0.0 ? (1.0 - local.x) / ray.x : ray.x < 0.0 ? -local.x / ray.x : 1.0e9,
                      ray.y > 0.0 ? (1.0 - local.y) / ray.y : ray.y < 0.0 ? -local.y / ray.y : 1.0e9,
                      ray.z > 0.0 ? (1.0 - local.z) / ray.z : ray.z < 0.0 ? -local.z / ray.z : 1.0e9);
    float length_ = min(exits.x, min(exits.y, exits.z));
    float depth = 0.0;
    for (int i = 0; i < FOG_SAMPLES; i++) {
        float t = (float(i) + 0.5) / float(FOG_SAMPLES) * length_;
        depth += sprayStrands(entry + ray * t, time) * SPRAY_DENSITY;
    }
    depth *= length_ / float(FOG_SAMPLES);
    float alpha = (1.0 - exp(-depth)) * SPRAY_MOST;

    // grainy, as the mist texture: grains on the face's pixels, along the
    // strands where they cross the face, in three layers streaming each its
    // own way and tossed about by the flow - each face of a stack its own;
    // smooth again far off, where its pixels get smaller than the screen's
    float strands = sprayStrands(entry, time);
    float step_ = float(SPRAY_SWIRL) * FLUID_STEP * time;
    int layer = int(dot(cell, abs(n)) + 0.5) & 63;
    float grain = 0.0;
    for (int k = 0; k < 3; k++) {
        vec3 at = entry - SPRAY_STREAMS[k] * step_ + sprayFlow(entry + float(k) * 7.0, time, 0.8);
        ivec2 px = ivec2(floor(vec2(dot(at, axisU), dot(at, axisV)) / FOG_PIXEL)) & 1023;
        float r = fluidRand(ivec4(px, layer, 842 + k));
        grain = max(grain, step(r, strands * 0.6) * (0.6 + 0.4 * fluidRand(ivec4(px, layer, 846 + k))));
    }
    float sharp = SPRAY_GRAIN * (1.0 - smoothstep(0.5, 1.5, max(length(f.dx), length(f.dy)) / FOG_PIXEL));
    alpha = max(alpha * (1.0 - 0.6 * sharp), grain * 0.45 * sharp);
    alpha *= smoothstep(FOG_CLEAR * 0.3, FOG_CLEAR, length(f.pos)) * 0.7 + 0.3 * smoothstep(0.2, 0.6, length(f.pos));
    return vec4(SPRAY_COLOR * (1.0 + 0.12 * grain * sharp), alpha);
}

// ---------------------------------------------------------------- volumes

// fluidNoise3, the same noise, made cheaper for volumes, which look it up a
// great many times: each axis wrapped once rather than at every corner, the
// corners' hashes built from the axes' parts.
float volumeNoise(vec3 p, float cells, int salt) {
    vec3 g = p * cells;
    ivec3 c = ivec3(floor(g));
    vec3 f = fract(g);
    f = f * f * (3.0 - 2.0 * f);
    int period = int(64.0 * cells + 0.5);
    ivec3 c0 = c - period * ivec3(floor(vec3(c) / float(period)));
    ivec3 c1 = c0 + 1 - period * ivec3(equal(c0 + 1, ivec3(period)));
    uint s = uint(salt) * 2654435761u;
    uint x0 = uint(c0.x) * 73856093u, x1 = uint(c1.x) * 73856093u;
    uint y0 = uint(c0.y) * 19349663u ^ s, y1 = uint(c1.y) * 19349663u ^ s;
    uint z0 = uint(c0.z) * 83492791u, z1 = uint(c1.z) * 83492791u;
    uvec4 lo = uvec4(x0 ^ y0, x1 ^ y0, x0 ^ y1, x1 ^ y1);
    uvec4 h0 = lo ^ uvec4(z0), h1 = lo ^ uvec4(z1);
    h0 ^= h0 >> 13u; h0 *= 0x5bd1e995u; h0 ^= h0 >> 15u;
    h1 ^= h1 >> 13u; h1 *= 0x5bd1e995u; h1 ^= h1 >> 15u;
    vec4 v = mix(vec4(h0 & 0xFFFFu), vec4(h1 & 0xFFFFu), f.z) / 65535.0;
    vec2 v2 = mix(v.xz, v.yw, f.x);
    return mix(v2.x, v2.y, f.y);
}

// The way the light falls on clouds and smoke: from above, a little from the
// south-west.
const vec3 VOLUME_SUN = vec3(0.24, 0.94, -0.24);

// How much of a cloud there is at world (blocks), e its place in its box, -1
// to 1 each way, time seconds into the day: more than CLOUD_COVER in its
// heaps, which thin out towards its box's edge, faster beneath. Coarse, only
// its heaps, for shadows; not fine, without its smallest lumps, for far off.
float volumeCloud(vec3 world, vec3 e, float time, bool coarse, bool fine) {
    vec3 s = vec3(e.x, e.y < 0.0 ? e.y * CLOUD_FLAT : e.y, e.z);
    vec3 q = world - vec3(float(CLOUD_DRIFT), 0.0, 0.0) * FLUID_STEP * time;
    float n = volumeNoise(q, 1.0 / CLOUD_HEAP, 850) * 0.5 + volumeNoise(q + 17.0, 2.0 / CLOUD_HEAP, 851) * 0.25;
    if (coarse) return n + 0.125 - CLOUD_SWELL * dot(s, s);
    // lumps on them, and smaller lumps on those, churning slowly in place,
    // a whole number of times a day
    vec3 churn = vec3(1.0, -1.0, 1.0) * FLUID_STEP * time * 2.0;
    n += volumeNoise(q - churn, 4.0 / CLOUD_HEAP, 852) * 0.15;
    n += fine ? volumeNoise(q + churn + 5.0, 8.0 / CLOUD_HEAP, 853) * 0.1 : 0.05;
    return n - CLOUD_SWELL * dot(s, s);
}

// How much of the smoke column there is at q - the world, risen and rolled -
// local its place from its slice's middle, reach how far the slice reaches,
// top whether it is the top slice: more than SMOKE_COVER in its billows,
// which thin out towards its edge, and up the top slice. Coarse, only its
// billows, for shadows.
float volumeColumn(vec3 q, vec3 local, vec3 reach, bool top, bool coarse) {
    float n = volumeNoise(q, 1.0 / SMOKE_BILLOW, 870) * 0.55 + volumeNoise(q + 17.0, 2.0 / SMOKE_BILLOW, 871) * 0.3;
    n += coarse ? 0.075 : volumeNoise(q + 5.0, 4.0 / SMOKE_BILLOW, 872) * 0.15;
    float r = length(local.xz) / SMOKE_RADIUS;
    float f = n - SMOKE_SWELL * r * r;
    if (top) {
        float h = clamp(local.y / reach.y * 0.5 + 0.5, 0.0, 1.0);
        f -= 0.6 * h * h;
    }
    return f;
}

// How much of a chimney's smoke there is at world, local its place from its
// box's middle, reach how far the box reaches, time seconds into the day: a
// thin plume rising from the block, widening and swaying as it goes, and
// thinning out to its top.
float volumeChimney(vec3 world, vec3 local, vec3 reach, float time) {
    float h = clamp((local.y + reach.y) / CHIMNEY_HEIGHT, 0.0, 1.0);
    float r = length(local.xz) / (CHIMNEY_BASE + h * CHIMNEY_HEIGHT * CHIMNEY_SPREAD);
    vec3 q = world - vec3(1.0, float(CHIMNEY_RISE), 0.0) * FLUID_STEP * time;
    q.xz += (vec2(volumeNoise(q, 0.5, 890), volumeNoise(q + 9.0, 0.5, 891)) - 0.5) * (0.5 + 1.5 * h);
    float n = volumeNoise(q, 1.0, 892) * 0.6 + volumeNoise(q + 3.0, 2.0, 893) * 0.4;
    return n - 0.5 * r * r - 0.5 * h * h;
}

// Where the view along ray, from the camera, enters and leaves the ellipsoid
// round centre with radii: (1, 0) if it misses it.
vec2 volumeThrough(vec3 centre, vec3 radii, vec3 ray) {
    vec3 o = -centre / radii, d = ray / radii;
    float a = dot(d, d), b = dot(o, d), c = dot(o, o) - 1.0;
    float h = b * b - a * c;
    if (h <= 0.0) return vec2(1.0, 0.0);
    h = sqrt(h);
    return vec2(-b - h, -b + h) / a;
}

// A volume's colour - over the light - and opacity, for the fragment at pos
// (relative to the camera) of its spread face: kind, its block's middle
// relative to the camera and in the world mod 64, from the vertex shader;
// time seconds into the day. Along the view through its box - and only
// through the round part of it its heaps or billows can reach - it is looked
// at every VOLUME_STEP blocks or so, at most VOLUME_LOOKS times, nearest
// first, each look hiding what is behind it, a little further along for each
// pixel, by chance, so the looks' layers don't show. Where it can't be, it
// isn't looked for.
vec4 volumeLook(int kind, vec3 blockRel, vec3 block, vec3 pos, float time) {
    vec3 middle, reach;
    volumeBox(kind, block, middle, reach);
    vec3 centre = blockRel + middle;
    vec3 ray = normalize(pos);
    vec3 safe = vec3(abs(ray.x) > 1.0e-6 ? ray.x : 1.0e-6, abs(ray.y) > 1.0e-6 ? ray.y : 1.0e-6, abs(ray.z) > 1.0e-6 ? ray.z : 1.0e-6);
    vec3 a = (centre - reach) / safe, b = (centre + reach) / safe;
    vec3 lo = min(a, b), hi = max(a, b);
    float t0 = max(max(max(lo.x, lo.y), lo.z), 0.05);
    float t1 = min(min(hi.x, hi.y), hi.z);
    bool cloud = kind == VOLUME_CLOUD, chimney = kind == VOLUME_CHIMNEY, top = kind == VOLUME_COLUMN_TOP;
    // the round part: as far out as its noise, at its most, outdoes its
    // thinning towards the edge (a cloud's, its top half's: its bottom half
    // is flatter, inside that)
    vec2 through = vec2(-1.0e9, 1.0e9);
    if (cloud) through = volumeThrough(centre, reach * sqrt((1.0 - CLOUD_COVER + CLOUD_EDGE) / CLOUD_SWELL), ray);
    else if (!chimney) through = volumeThrough(centre, vec3(vec2(sqrt((1.0 - SMOKE_COVER + SMOKE_EDGE) / SMOKE_SWELL) * SMOKE_RADIUS), 1.0e6).xzy, ray);
    t0 = max(t0, through.x);
    t1 = min(t1, through.y);
    if (t1 <= t0) return vec4(0.0);

    float density = cloud ? CLOUD_DENSITY : chimney ? CHIMNEY_DENSITY : SMOKE_DENSITY;
    float wanted = VOLUME_STEP * (cloud ? 1.0 : chimney ? 0.4 : 1.5);
    int looks = int(clamp(ceil((t1 - t0) / wanted), 2.0, float(VOLUME_LOOKS)));
    float stepLen = (t1 - t0) / float(looks);
    // (the smoke column is wide, and much of the way into it is its thin
    // edge: it is looked at often enough to reach across it, only looks where
    // it can be counting towards VOLUME_LOOKS)
    bool column = !cloud && !chimney;
    if (column) {
        looks = int(ceil((t1 - t0) / max(wanted, (t1 - t0) / float(VOLUME_LOOKS * 2))));
        stepLen = (t1 - t0) / float(looks);
    }
    int counted = 0;
    float jitter = fluidRand(ivec4(ivec2(gl_FragCoord.xy), 0, 899));
    // the column's rise, and the slower field rolling it, drifting about
    vec3 rise = vec3(0.0, float(SMOKE_RISE), 0.0) * FLUID_STEP * time;
    vec3 rollDrift = vec3(2.0, float(SMOKE_RISE) - 4.0, -1.0) * FLUID_STEP * time;
    vec3 color = vec3(0.0);
    float clear = 1.0;
    for (int i = 0; i < VOLUME_LOOKS * 4; i++) {
        if (i >= looks || counted >= VOLUME_LOOKS) break;
        float t = t0 + (float(i) + jitter) * stepLen;
        vec3 local = ray * t - centre;
        vec3 world = block + middle + local;
        float here;
        vec3 shade;
        if (cloud) {
            vec3 e = local / reach;
            if (1.0 - CLOUD_SWELL * dot(e, e) < CLOUD_COVER - CLOUD_EDGE) continue;
            counted++;
            here = smoothstep(CLOUD_COVER - CLOUD_EDGE, CLOUD_COVER + CLOUD_EDGE, volumeCloud(world, e, time, false, t < 24.0));
            if (here <= 0.0) continue;
            // lit by how much of its heaps lies towards the light, and how
            // deep in it is; the fires' glow on its shadowed underside
            vec3 up = VOLUME_SUN * CLOUD_HEAP * 0.5;
            float above = smoothstep(CLOUD_COVER - CLOUD_EDGE, CLOUD_COVER + CLOUD_EDGE, volumeCloud(world + up, (local + up) / reach, time, true, false));
            float light = exp(-(above + 0.5 * clamp(0.6 - e.y, 0.0, 1.0)) * CLOUD_SHADOW);
            shade = mix(CLOUD_DARK, CLOUD_LIT, light) + CLOUD_GLOW * CLOUD_GLOWING * (1.0 - light) * clamp(-e.y * 2.0, 0.0, 1.0);
        } else if (chimney) {
            here = smoothstep(0.25, 0.45, volumeChimney(world, local, reach, time));
            if (here <= 0.0) continue;
            shade = CHIMNEY_COLOR * mix(0.7, 1.1, clamp((local.y + reach.y) / CHIMNEY_HEIGHT, 0.0, 1.0));
        } else {
            float r = length(local.xz) / SMOKE_RADIUS;
            if (1.0 - SMOKE_SWELL * r * r < SMOKE_COVER - SMOKE_EDGE) continue;
            counted++;
            vec3 roll = vec3(volumeNoise(world - rollDrift, 1.0 / 16.0, 860) - 0.5, 0.0, volumeNoise(world - rollDrift + 23.0, 1.0 / 16.0, 861) - 0.5) * 2.0 * SMOKE_ROLL;
            vec3 q = world - rise + roll;
            here = smoothstep(SMOKE_COVER - SMOKE_EDGE, SMOKE_COVER + SMOKE_EDGE, volumeColumn(q, local, reach, top, false));
            if (here <= 0.0) continue;
            // lit by how much of it lies towards the light, and how far in
            // from its edge; the fires' glow deep in its shadow
            vec3 up = VOLUME_SUN * SMOKE_BILLOW * 0.5;
            float above = smoothstep(SMOKE_COVER - SMOKE_EDGE, SMOKE_COVER + SMOKE_EDGE, volumeColumn(q + up, local + up, reach, top, true));
            float light = exp(-(above + 0.5 * clamp(1.0 - r, 0.0, 1.0)) * SMOKE_SHADOW);
            shade = mix(SMOKE_DARK, SMOKE_LIT, light) + SMOKE_GLOW * SMOKE_GLOWING * (1.0 - light);
        }
        float a = 1.0 - exp(-here * density * stepLen);
        color += clear * a * shade;
        clear *= 1.0 - a;
        if (clear < 0.02) break;
    }
    float alpha = 1.0 - clear;
    return vec4(color / max(alpha, 1.0e-4), alpha);
}
