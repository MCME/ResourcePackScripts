// Marble: white veins with a thinner yellow strip following each and the
// faintest touch of red, drawn over a pack's marble textures (its
// .mcme-shaders.json "marble") from the world position, so that they run on
// across blocks and faces as if every block were cut from one slab. The
// texture underneath shows through as the stone; only texels of its green
// (MARBLE_GREEN_) get veins, so inlays and carving stay as they are.
// Pixelated as a 16px texture is (MARBLE_PIXEL). Its settings are in
// marble_config.glsl. Needs fluid.glsl, which tells its faces from others
// (fluidKind): the sync signs the pack's marble textures as FLUID_MARBLE.
//
// The veins are cracks: the walls between cells around random points, only
// some of them, so that they fork and end rather than close: most of those
// running with the stone's flow, which turns across it, so that they join up
// into long veins, and a few across it. They thicken, thin and fade along
// their length, and there are more of them in some areas than others.
// They gather in clouds sweeping across tens of blocks (marbleClouds), and
// the stone's tone changes slowly across them.

#define MARBLE FLUID_MARBLE

// How far from a wall its vein can reach, in pixels: its white at its widest,
// its yellow and red beyond, or its branches; and a branch's.
#define MARBLE_REACH max(max(MARBLE_WIDTH_MAX * (1.0 + MARBLE_SOFT) + 2.0, MARBLE_BRANCH_LENGTH), MARBLE_YELLOW_OFFSET + MARBLE_YELLOW_DRIFT + max(MARBLE_RED_OFFSET + MARBLE_RED_DRIFT, MARBLE_YELLOW_BLUR * 2.5) + 1.5)
#define MARBLE_BRANCH_REACH (MARBLE_BRANCH_WIDTH_MAX * (1.0 + MARBLE_SOFT) + 2.0)

// Four smooth 3D value noises at once, with cells per block, repeating every
// 64 blocks as the position they are given does: 64 * cells must be whole.
// Each 0 to 1.
vec4 marbleNoise(vec3 p, float cells, int salt) {
    vec3 q = p * cells;
    vec3 i = floor(q);
    vec3 f = q - i;
    f = f * f * (3.0 - 2.0 * f);
    float n = floor(64.0 * cells + 0.5);
    vec4 v[8];
    for (int k = 0; k < 8; k++) {
        // wrapped in floats: % of a negative int is undefined in GLSL
        vec3 c = i + vec3(k & 1, (k >> 1) & 1, k >> 2);
        c -= n * floor(c / n);
        uint h = fluidHash(ivec4(ivec3(c), salt));
        v[k] = vec4(h & 255u, (h >> 8) & 255u, (h >> 16) & 255u, h >> 24) / 255.0;
    }
    return mix(mix(mix(v[0], v[1], f.x), mix(v[2], v[3], f.x), f.y),
               mix(mix(v[4], v[5], f.x), mix(v[6], v[7], f.x), f.y), f.z);
}


// How much of a line of half width (pixels) this is, at a distance (pixels)
// from its middle, its edge soft over so many pixels each way.
float marbleBlur(float distance, float width, float soft) {
    return 1.0 - smoothstep(width + 0.5 - soft, width + 0.5 + soft, abs(distance));
}

// ...with a pixel's soft edge, softer as it widens (MARBLE_SOFT), so that the
// wide fade into the stone.
float marbleLine(float distance, float width) {
    return marbleBlur(distance, width, 0.5 + max(width, 0.0) * MARBLE_SOFT);
}

// Cell c's random point, in cells; wrap is the cells in 64 blocks.
vec3 marblePoint(vec3 c, float wrap, int salt) {
    vec3 w = c - wrap * floor(c / wrap);
    uint h = fluidHash(ivec4(ivec3(w), salt));
    return c + 0.5 + (vec3(h & 1023u, (h >> 10) & 1023u, (h >> 20) & 1023u) / 1023.0 - 0.5) * MARBLE_JITTER;
}

// The wall between neighbouring cells a and b's hash: the same from either.
uint marbleWall(vec3 a, vec3 b, float wrap, int salt) {
    vec3 d = b - a;
    float k = d.x * 25.0 + d.y * 5.0 + d.z;
    vec3 c = k < 0.0 ? b : a;
    c -= wrap * floor(c / wrap);
    return fluidHash(ivec4(ivec3(c), salt + int(abs(k)) * 7919));
}

// The 27 cells round one, in cells towards the side of it a point is on (+1)
// or away (-1): the eight round that corner of it first, which nearly always
// hold the point nearest, so that the search can pass over most of the rest
const vec3 MARBLE_AROUND[27] = vec3[27](
    vec3(0, 0, 0), vec3(1, 0, 0), vec3(0, 1, 0), vec3(0, 0, 1),
    vec3(1, 1, 0), vec3(1, 0, 1), vec3(0, 1, 1), vec3(1, 1, 1),
    vec3(-1, 0, 0), vec3(0, -1, 0), vec3(0, 0, -1),
    vec3(-1, 1, 0), vec3(-1, 0, 1), vec3(1, -1, 0), vec3(0, -1, 1), vec3(1, 0, -1), vec3(0, 1, -1),
    vec3(-1, -1, 0), vec3(-1, 0, -1), vec3(0, -1, -1),
    vec3(-1, 1, 1), vec3(1, -1, 1), vec3(1, 1, -1),
    vec3(-1, -1, 1), vec3(-1, 1, -1), vec3(1, -1, -1),
    vec3(-1, -1, -1));

struct MarbleVeins {
    float white, yellow, red;   // how much of each this pixel is
    float near;                 // how far it is from the nearest vein, in pixels (up to reach)
};

// One web of veins at q, on a face of normal n: cells per block, how many of
// their walls are veins (across the flow, and along it: those that run on
// into long veins), their half width here (pixels) and strength, how far the
// yellow is from the white here (offset) and the red beyond it (offsetR), in
// pixels, and the yellow's half width, soft edge (pixels) and strength here,
// if it has them (stripes), and how far from a wall they reach.
MarbleVeins marbleVeins(vec3 q, vec3 n, vec3 flow, float cells, float across, float along,
                        float width, float alpha, float offset, float offsetR, vec3 yellow,
                        bool stripes, float reach, int salt) {
    vec3 s = q * cells;
    vec3 i = floor(s);
    float wrap = floor(64.0 * cells + 0.5);

    // the cell it is in: the nearest point's. The eight cells round the
    // corner of s's own cell that it is nearest nearly always hold that
    // point; of the rest, only those whose point could be nearer still are
    // looked at
    vec3 a = i;
    vec3 pa = vec3(0.0);
    float best = 1.0e9;
    vec3 toward = step(0.5, s - i) * 2.0 - 1.0;
    for (int k = 0; k < 8; k++) {
        vec3 c = i + MARBLE_AROUND[k] * toward;
        vec3 pt = marblePoint(c, wrap, salt);
        float dd = dot(pt - s, pt - s);
        if (dd < best) {
            best = dd;
            a = c;
            pa = pt;
        }
    }
    float near8 = best;
    for (int k = 8; k < 27; k++) {
        vec3 c = i + MARBLE_AROUND[k] * toward;
        vec3 lo = c + 0.5 - 0.5 * MARBLE_JITTER;
        vec3 gap = max(max(lo - s, s - lo - MARBLE_JITTER), 0.0);
        if (dot(gap, gap) >= near8) continue;
        vec3 pt = marblePoint(c, wrap, salt);
        float dd = dot(pt - s, pt - s);
        if (dd < best) {
            best = dd;
            a = c;
            pa = pt;
        }
    }

    // and the walls around it that are veins, near enough to show
    MarbleVeins v = MarbleVeins(0.0, 0.0, 0.0, 1.0e9);
    float pixels = 1.0 / (cells * MARBLE_PIXEL);    // pixels per cell
    float far = reach / pixels;     // a wall further off, in cells, is out of reach (along the face it is no nearer)
    for (int k = 0; k < 27; k++) {
        if (k == 13) continue;
        vec3 b = a + vec3(k % 3, (k / 3) % 3, k / 9) - 1.0;
        // passed over unless its point could make a wall in reach: as near
        // to s, and as far from a's, as it can be
        vec3 lo = b + 0.5 - 0.5 * MARBLE_JITTER;
        vec3 hi = lo + MARBLE_JITTER;
        vec3 gap = max(max(lo - s, s - hi), 0.0);
        vec3 span = max(abs(lo - pa), abs(hi - pa));
        if (dot(gap, gap) - best > 2.0 * far * length(span)) continue;
        vec3 pb = marblePoint(b, wrap, salt);
        // its wall's distance across, cheaply first: along the face it is
        // no nearer
        if ((dot(pb - s, pb - s) - best) * 0.5 * inversesqrt(dot(pb - pa, pb - pa)) > far) continue;
        vec3 m = normalize(pb - pa);
        // how far into a's cell from the wall, in pixels along the face (so
        // that a wall cut at a slant is no wider); a wall cut along the face
        // would be a smear, not a vein
        float slant = length(m - n * dot(n, m));
        if (slant < MARBLE_SLANT) continue;
        float dist = dot(0.5 * (pa + pb) - s, m) / slant * pixels;
        if (dist > reach) continue;
        uint h = marbleWall(a, b, wrap, salt + 1);
        float share = mix(across, along, 1.0 - smoothstep(0.4, 0.75, abs(dot(m, flow))));
        if (float(h & 255u) >= share * 256.0) continue;
        v.near = min(v.near, dist);

        // a little of their own, wall by wall; the wide fainter, so that the
        // stone shows through
        float w = width + (float((h >> 8) & 255u) / 255.0 - 0.5) * MARBLE_WIDTH_JITTER;
        float o = alpha * mix(0.75, 1.0, float((h >> 16) & 255u) / 255.0)
                * smoothstep(MARBLE_SLANT, 2.0 * MARBLE_SLANT, slant);
        v.white = max(v.white, marbleLine(dist, w) * o * mix(1.0, MARBLE_WIDE_ALPHA, smoothstep(0.0, MARBLE_WIDTH_MAX, w)));
        // the yellow on one side of it, now and then across; the red beyond
        if (stripes && float((h >> 25) & 7u) < MARBLE_YELLOW_SHARE * 8.0) {
            // which side: dist is how far into this pixel's own cell, so
            // told by which of the wall's two cells that is - the one it is
            // keyed to (marbleWall) or the other - for the same side from both
            bool flip = ((h >> 24) & 1u) != 0u;
            bool keyed = dot(b - a, vec3(25.0, 5.0, 1.0)) > 0.0;
            float side = flip != keyed ? dist : -dist;
            v.yellow = max(v.yellow, marbleBlur(side - offset, yellow.x, yellow.y) * yellow.z * o);
            if (float(h >> 28) < MARBLE_RED_SHARE * 16.0) {
                v.red = max(v.red, marbleLine(side - offset - offsetR, MARBLE_RED_WIDTH) * o);
            }
        }
    }
    return v;
}

// The same web, white only, flat on a face of normal n: its cells squares on
// the world's plane across n's largest axis rather than cubes, for about a
// third of the work. So its veins do not run on round corners, which faint
// thin ones need not, and none are cut at a slant.
float marbleFlatVeins(vec3 q, vec3 n, vec3 flow, float cells, float across, float along,
                      float width, float alpha, float reach, int salt) {
    vec3 an = abs(n);
    vec2 s = q.xy;
    vec2 way = flow.xy;
    if (an.x >= an.y && an.x >= an.z) {
        s = q.yz;
        way = flow.yz;
        salt += 97;
    } else if (an.y >= an.z) {
        s = q.xz;
        way = flow.xz;
        salt += 194;
    }
    s *= cells;
    vec2 i = floor(s);
    float wrap = floor(64.0 * cells + 0.5);

    // the cell it is in: the nearest point's
    vec2 a = i;
    vec2 pa = vec2(0.0);
    float best = 1.0e9;
    for (int k = 0; k < 9; k++) {
        vec2 c = i + vec2(k % 3, k / 3) - 1.0;
        vec2 pt = marblePoint(vec3(c, 0.0), wrap, salt).xy;
        float dd = dot(pt - s, pt - s);
        if (dd < best) {
            best = dd;
            a = c;
            pa = pt;
        }
    }

    // and the walls around it that are veins, near enough to show
    float white = 0.0;
    float pixels = 1.0 / (cells * MARBLE_PIXEL);    // pixels per cell
    for (int k = 0; k < 9; k++) {
        if (k == 4) continue;
        vec2 b = a + vec2(k % 3, k / 3) - 1.0;
        vec2 pb = marblePoint(vec3(b, 0.0), wrap, salt).xy;
        vec2 m = normalize(pb - pa);
        float dist = dot(0.5 * (pa + pb) - s, m) * pixels;
        if (dist > reach) continue;
        uint h = marbleWall(vec3(a, 0.0), vec3(b, 0.0), wrap, salt + 1);
        float share = mix(across, along, 1.0 - smoothstep(0.4, 0.75, abs(dot(m, way))));
        if (float(h & 255u) >= share * 256.0) continue;
        float w = width + (float((h >> 8) & 255u) / 255.0 - 0.5) * MARBLE_WIDTH_JITTER;
        float o = alpha * mix(0.75, 1.0, float((h >> 16) & 255u) / 255.0);
        white = max(white, marbleLine(dist, w) * o * mix(1.0, MARBLE_WIDE_ALPHA, smoothstep(0.0, MARBLE_WIDTH_MAX, w)));
    }
    return white;
}

// The clouds the veins gather in at p: how much of one this is, 0 to 1 -
// where a smooth noise, bent, is near its middle, so that they sweep across
// tens of blocks, fading in and out along their length - and the noise the
// stone's tone follows, 0 to 1, which changes across them.
vec2 marbleClouds(vec3 p) {
    vec4 bend = marbleNoise(p, MARBLE_CLOUD_CELLS, 1900);
    vec4 c = marbleNoise(p + MARBLE_CLOUD_BEND * (bend.xyz - 0.5), MARBLE_CLOUD_CELLS, 1910);
    float cloud = (1.0 - smoothstep(0.5 * MARBLE_CLOUD_WIDTH, MARBLE_CLOUD_WIDTH, abs(c.x - 0.5)))
                * smoothstep(0.9 - MARBLE_CLOUD_SHARE, 1.1 - MARBLE_CLOUD_SHARE, c.y);
    return vec2(cloud, c.x);
}

// The marble over its texel's colour: lit is the light on it (its vertex
// colour times the light map), so that colour / lit is the texel itself.
vec3 marbleColor(vec3 color, vec3 lit, FluidFrame f) {
    // the stone: texels of the green, not inlays or carving. Got back from
    // the lit colour only to within rounding, which shifts as the light map
    // does (torches flicker every tick): so told by limits a third of a
    // step off the texels' own whole steps, or one on a limit would flicker
    vec3 texel = color / max(lit, vec3(1.0e-3)) * 255.0;
    if (texel.g < MARBLE_GREEN_MIN - 0.3 || texel.g > MARBLE_GREEN_MAX + 0.3
            || texel.g < texel.r + 5.7 || texel.g < texel.b + 7.7 || abs(texel.r - texel.b) > 14.3) {
        return color;
    }

    // the middle of this pixel of the block, half a pixel in from the face
    vec3 n = fluidNormal(f);
    vec3 p = f.world - n * (0.5 * MARBLE_PIXEL);
    p = (floor(p / MARBLE_PIXEL) + 0.5) * MARBLE_PIXEL;

    // folded twice over, the second fold by the first, as marble is: what
    // curls the veins; and wavering finely, so that they are not straight.
    // The noises' fourth parts: how thick the veins are here, how far the
    // yellow drifts, and how much they swell
    vec4 fold = marbleNoise(p, MARBLE_CURL_CELLS, 1800) - 0.5;
    vec3 q = p + MARBLE_CURL * fold.xyz;
    vec4 fold2 = marbleNoise(q, MARBLE_CURL_FINE_CELLS, 1810) - 0.5;
    q += MARBLE_CURL_FINE * fold2.xyz;
    vec4 jag = marbleNoise(p, MARBLE_JAG_CELLS, 1820) - 0.5;
    q += MARBLE_JAG * jag.xyz;

    // the way the long veins run, turning across the stone, and the patches
    // they die out in
    vec4 flow = marbleNoise(q, MARBLE_FLOW_CELLS, 1700);
    // the clouds the veins gather in, and the stone's tone across them; and
    // how strong the veins are along their length, and how far the red drifts
    vec2 clouds = marbleClouds(q);
    vec4 look2 = marbleNoise(q, MARBLE_ALONG_CELLS, 1530);

    float busy = clouds.x;
    // and the stone's dark spots, feathered far out
    float spot = 1.0 - smoothstep(MARBLE_DARK_CORE, MARBLE_DARK_CORE + MARBLE_DARK_FEATHER, clouds.y);
    float strength = mix(MARBLE_FADE, 1.0, smoothstep(0.2, 0.7, flow.w)) * mix(MARBLE_QUIET_ALPHA, 1.0, busy);
    float quiet = mix(MARBLE_QUIET, 1.0, busy);
    float thickness = smoothstep(0.25, 0.85, fold.w + 0.5);
    thickness *= thickness;
    float swell = jag.w * 2.0 * MARBLE_SWELL;
    float alpha = mix(MARBLE_ALPHA_MIN, 1.0, smoothstep(0.2, 0.8, look2.x));

    // the yellow follows the white roughly: its own drift nearer and
    // further, now and then across it; the red drifts off the yellow
    float offset = MARBLE_YELLOW_OFFSET + fold2.w * 2.0 * MARBLE_YELLOW_DRIFT;
    float offsetR = MARBLE_RED_OFFSET + (look2.y - 0.5) * 2.0 * MARBLE_RED_DRIFT;
    // and fades along its length, now and then blurring as it widens
    float blur = smoothstep(1.0 - MARBLE_YELLOW_BLUR_SHARE - 0.1, 1.0 - MARBLE_YELLOW_BLUR_SHARE + 0.1, look2.w);
    vec3 yellowLook = vec3(MARBLE_YELLOW_WIDTH + blur * MARBLE_YELLOW_BLUR,
                           0.5 + blur * MARBLE_YELLOW_BLUR * 1.5,
                           mix(MARBLE_YELLOW_FADE, 1.0, smoothstep(0.25, 0.7, look2.z)) * mix(1.0, MARBLE_YELLOW_BLUR_ALPHA, blur));

    vec3 way = normalize(flow.xyz - 0.5 + vec3(1.0e-4));
    MarbleVeins veins = marbleVeins(q, n, way, MARBLE_VEINS, MARBLE_SHARE_ACROSS * quiet,
                                    MARBLE_SHARE_ALONG * mix(MARBLE_QUIET_ALONG, 1.0, busy),
                                    mix(MARBLE_WIDTH_MIN, MARBLE_WIDTH_MAX, thickness) + swell, alpha,
                                    offset, offsetR, yellowLook, true, MARBLE_REACH, 1300);
    float white = veins.white * MARBLE_WHITE_ALPHA;
    // the branches: a finer web, mostly with the flow, near the veins in the
    // clouds and anywhere in the dark spots (and only worked out there)
    float lines = max(busy, spot * MARBLE_DARK_LINES);
    if (lines > 0.0 && (veins.near < MARBLE_BRANCH_LENGTH || spot > 0.0)) {
#if MARBLE_FLAT_BRANCHES
        float fine = marbleFlatVeins(q, n, way, MARBLE_BRANCH_CELLS, MARBLE_BRANCH_SHARE * MARBLE_BRANCH_ACROSS * lines,
                                     MARBLE_BRANCH_SHARE * lines,
                                     mix(MARBLE_WIDTH_MIN, MARBLE_BRANCH_WIDTH_MAX, thickness) + swell * 0.5,
                                     alpha, MARBLE_BRANCH_REACH, 1400);
#else
        float fine = marbleVeins(q, n, way, MARBLE_BRANCH_CELLS, MARBLE_BRANCH_SHARE * MARBLE_BRANCH_ACROSS * lines,
                                 MARBLE_BRANCH_SHARE * lines,
                                 mix(MARBLE_WIDTH_MIN, MARBLE_BRANCH_WIDTH_MAX, thickness) + swell * 0.5,
                                 alpha, 0.0, 0.0, vec3(0.0), false, MARBLE_BRANCH_REACH, 1400).white;
#endif
        float shown = max(1.0 - smoothstep(0.0, MARBLE_BRANCH_LENGTH, veins.near), spot);
        white = max(white, fine * MARBLE_BRANCH_ALPHA * shown);
    }
    white *= strength;
    float yellow = veins.yellow * MARBLE_YELLOW_ALPHA * strength;
    float reds = veins.red * MARBLE_RED_ALPHA * strength;

    // the stone's tone; the veins take its own light and grain
    color *= mix(MARBLE_TONE, 1.0 - MARBLE_DARK, spot)
           * (1.0 + MARBLE_LIGHT * smoothstep(MARBLE_DARK_CORE + MARBLE_DARK_FEATHER, 1.0 - MARBLE_DARK_CORE, clouds.y));
    float grainShade = sqrt(dot(texel / 255.0, vec3(0.333)) / MARBLE_GREEN_MEAN);
    color = mix(color, MARBLE_RED * lit * grainShade, reds);
    color = mix(color, MARBLE_YELLOW * lit * grainShade, yellow);
    return mix(color, MARBLE_WHITE * lit * grainShade, white);
}
