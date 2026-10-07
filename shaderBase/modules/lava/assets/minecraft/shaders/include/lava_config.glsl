// The lava's settings (lava.glsl). See lava.glsl for what it is.

#define LAVA_PIXEL (1.0 / 16.0)      // its pixels' size, in blocks, as a 16px texture's

// the molten layers under the surface, like the eye's nested spheres: each
// further down, coarser and slower than the one above
#define LAVA_LAYERS 4                // how many (up to 6)
#define LAVA_LAYER_DEPTH 0.18        // how far apart they are, in blocks
#define LAVA_HEAT 1.15               // how hot they burn: higher is yellower

// how fast it moves, slower than the eye's flames: in whole steps of 64
// blocks a day (0.053 blocks a second), so that it is back where it started
// when the day's clock starts over
#define LAVA_CHURN 1                 // still lava's stirring
#define LAVA_FLOW_STEPS 6            // flowing lava, at its surface (0.32 a second; diagonally 1.41 times that)
#define LAVA_FALL_STEPS 17           // lava falling down a side (0.91 a second)

// the cooled crust floating on still lava, in shapeless rafts, cracked across
#define LAVA_CRUST_SIZE 4.0          // how big its rafts are, roughly, in blocks (a power of two)
#define LAVA_CRUST 0.55              // how much of still lava it covers, 0 to 1
#define LAVA_PLATE 2.0               // how far apart its main cracks are, roughly, in blocks (a power of two)
#define LAVA_CRACK 0.1               // how wide the widest cracks are, in blocks

// bubbles rising through still lava's open melt and bursting
#define LAVA_BUBBLE_SPACING 2.0      // at most one at a time in each square this wide, in blocks (a power of two)
#define LAVA_BUBBLES 0.45            // in how many of them, 0 to 1

#define LAVA_SHADING 0.55            // how much the game's shading of its sides darkens it, 0 to 1

// under a shader pack, which makes lava glow: how much more it glows than the
// pack's own lava - its emission, which its bloom and light come from (MCME's mod)
#define LAVA_GLOW 1.5
