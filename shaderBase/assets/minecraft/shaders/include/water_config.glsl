// The water's settings (water.glsl). See water.glsl for what it is.

#define WATER_PIXEL (1.0 / 16.0)     // its pixels' size, in blocks, as a 16px texture's

// ripples, in layers under the surface as the lava's are
#define WATER_LAYERS 3               // how many (up to 6)
#define WATER_LAYER_DEPTH 0.3        // how far apart they are, in blocks
#define WATER_RIPPLE 0.16            // how much they lighten and darken it
#define WATER_CREST 0.22             // how bright the light caught on their crests is
#define WATER_WAVE 0.35              // how much they tilt the surface, for its sheen

// how fast it moves, in whole steps of 64 blocks a day (0.053 blocks a
// second), so that it is back where it started when the day's clock starts over
#define WATER_STIR 2                 // still water's drift
#define WATER_FLOW_STEPS 12          // flowing water, on top (0.64 a second; diagonally 1.41 times that)
#define WATER_FALL_STEPS 30          // water falling down a side (1.6 a second)

// how see-through it is, and how it takes the sky's colour at a glance
#define WATER_ALPHA 0.5              // its opacity looking straight down...
#define WATER_ALPHA_GLANCE 0.9       // ...and looking along it
#define WATER_SHEEN 0.5              // how much of the sky's colour it takes, looking along it

// foam, white water
#define WATER_FOAM 0.3               // on flowing water's top, 0 to 1, more where it runs steeper
#define WATER_FALL_FOAM 0.5          // on falls
#define WATER_SHORE_FOAM 1.0         // along its shores - with Sodium only, see water.glsl
#define WATER_FOAM_COLOR vec3(0.92, 0.95, 0.96)
