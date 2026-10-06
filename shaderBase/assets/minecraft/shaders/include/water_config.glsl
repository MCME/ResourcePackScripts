// The water's settings (water.glsl). See water.glsl for what it is.

#define WATER_PIXEL (1.0 / 16.0)     // its pixels' size, in blocks, as a 16px texture's

// ripples, in layers under the surface as the lava's are
#define WATER_LAYERS 3               // how many (up to 6)
#define WATER_LAYER_DEPTH 0.3        // how far apart they are, in blocks
#define WATER_RIPPLE 0.16            // how much they lighten and darken it
#define WATER_CREST 0.22             // how bright the light caught on their crests is
#define WATER_STREAK 0.35            // how bright the streaks along flowing water are

// how fast it moves, in whole steps of 64 blocks a day (0.053 blocks a
// second), so that it is back where it started when the day's clock starts over
#define WATER_STIR 2                 // still water's drift
#define WATER_FLOW_STEPS 12          // flowing water, on top (0.64 a second; diagonally 1.41 times that)
#define WATER_FALL_STEPS 30          // water falling down a side (1.6 a second)

#define WATER_ALPHA 0.6              // how opaque it is, foam aside

// foam, white water: all of it blended in, no more than WATER_FOAM_OPACITY
#define WATER_FOAM_OPACITY 0.5
#define WATER_FOAM 0.3               // on flowing water's top, 0 to 1, more where it runs steeper
#define WATER_FALL_FOAM 0.4          // on falls
#define WATER_SHORE_FOAM 1.0         // along its shores - with Sodium only, see water.glsl
#define WATER_FOAM_COLOR vec3(0.92, 0.95, 0.96)

// small waves now and then on still water: a crest of foam crossing it,
// always from the west, or the north-west, a trail of foam behind it
#define WATER_WAVE_SPACING 8.0       // at most one at a time in each square this wide, in blocks (a power of two)
#define WATER_WAVES 0.25             // in how many of them, 0 to 1
#define WATER_WAVE_TRAVEL 4.0        // how far each crosses, in blocks (under WATER_WAVE_SPACING)
#define WATER_WAVE_TRAIL 1.6         // how long the trail behind it is, in blocks
#define WATER_WAVE_OPACITY 0.75      // how opaque its foam is at most
