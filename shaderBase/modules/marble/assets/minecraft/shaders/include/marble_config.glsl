// The marble's settings (marble.glsl). See marble.glsl for what it is.

#define MARBLE_PIXEL (1.0 / 16.0)    // its pixels' size, in blocks, as a 16px texture's

// the white veins: walls between cells around random points, this many cells
// per block (64 times it must be whole), only some of them veins: most of
// those running with the stone's flow, so that they join up into long veins,
// and a few across it
#define MARBLE_VEINS 0.5
#define MARBLE_SHARE_ALONG 0.97      // how many of the walls along the flow are veins, 0 to 1
#define MARBLE_SHARE_ACROSS 0.25     // and across it
#define MARBLE_FLOW_CELLS 0.125      // how quickly the flow turns: cells per block (64 times it must be whole)
#define MARBLE_JITTER 0.9            // how far the points stray from their cells' middles, 0 to 1
// how far the stone is folded before the veins are drawn, in blocks, and
// how many cells per block the folds have (64 times each must be whole):
// their curls; then again, more finely. Too far, and it folds over on
// itself, the veins piling up
#define MARBLE_CURL 1.0
#define MARBLE_CURL_CELLS 0.375
#define MARBLE_CURL_FINE 0.3
#define MARBLE_CURL_FINE_CELLS 0.75
#define MARBLE_JAG 0.04              // how far they waver, finely, in blocks
#define MARBLE_JAG_CELLS 1.5
#define MARBLE_ALONG_CELLS 0.375     // how quickly their strength, and the yellow's, change along them
#define MARBLE_WHITE vec3(0.70, 0.76, 0.66)
#define MARBLE_WHITE_ALPHA 0.6
// the veins' half width beyond the middle pixel's half, in pixels, along
// their length: from the thinnest to the widest (little of it is), how much
// they waver in that, and how much each bit of one differs from the next
#define MARBLE_WIDTH_MIN -0.25
#define MARBLE_WIDTH_MAX 0.6
#define MARBLE_SWELL 0.2
#define MARBLE_WIDTH_JITTER 0.3
#define MARBLE_ALPHA_MIN 0.5         // their faintest strength, the strongest's being 1
#define MARBLE_SOFT 0.5              // how much softer a vein's edge is for each pixel wider
#define MARBLE_WIDE_ALPHA 0.6        // the widest's strength, beside the thinnest's
#define MARBLE_SLANT 0.25            // the walls cut at less than this slant to the face fade out, 0 to 1
// the branches: a finer web, mostly with the flow, near the veins in the
// clouds and anywhere in the dark spots
#define MARBLE_BRANCH_CELLS 1.5
#define MARBLE_BRANCH_SHARE 0.4
#define MARBLE_BRANCH_ACROSS 0.4    // how many of those across the flow, beside along it
#define MARBLE_BRANCH_WIDTH_MAX 0.35
#define MARBLE_BRANCH_LENGTH 4.0     // how far from a vein, in pixels (further costs more)
#define MARBLE_BRANCH_ALPHA 0.6
// 1: worked out flat on each face, for about a third of the work, so that
// they do not run on round corners; 0: in 3D, as the veins are
#define MARBLE_FLAT_BRANCHES 1
// how the veins fade along their length: in patches as large as the flow's
// turns, never below this strength
#define MARBLE_FADE 0.5
// the clouds the veins gather in, sweeping across tens of blocks, the quiet
// stone between them keeping this much of the veins across the flow, of those
// along it, and of their strength (and none of the branches)
#define MARBLE_CLOUD_CELLS 0.0625    // cells per block (64 times it must be whole)
#define MARBLE_CLOUD_BEND 8.0        // how far they are bent, in blocks
#define MARBLE_CLOUD_WIDTH 0.15      // how wide, as a share of the noise they follow, 0 to 0.5
#define MARBLE_CLOUD_SHARE 0.6       // how much of their length shows, 0 to 1
#define MARBLE_QUIET 0.15
#define MARBLE_QUIET_ALONG 0.75
#define MARBLE_QUIET_ALPHA 0.5
// the stone's tone, changing slowly across the clouds: in general, beside the
// texture's; its dark spots' at their darkest, as much darker than the
// texture, where the noise they follow is below this, fading out over so much
// more of it (wider is softer); and the lightest stone, as much lighter
#define MARBLE_TONE 0.95
#define MARBLE_DARK 0.15
#define MARBLE_DARK_CORE 0.15
#define MARBLE_DARK_FEATHER 0.4
#define MARBLE_LIGHT 0.1
#define MARBLE_DARK_LINES 0.5        // the branches in the dark spots, away from the veins too, as many as in the clouds

// the yellow strip roughly following the white veins, on some of them
#define MARBLE_YELLOW vec3(0.74, 0.64, 0.33)
#define MARBLE_YELLOW_SHARE 0.5      // how many of the veins have it, 0 to 1
#define MARBLE_YELLOW_OFFSET 2.0     // how far from the white's middle, in pixels, on average
#define MARBLE_YELLOW_DRIFT 1.0      // how far it strays from that, nearer or further (further costs more)
#define MARBLE_YELLOW_WIDTH 0.0
#define MARBLE_YELLOW_ALPHA 0.75
#define MARBLE_YELLOW_FADE 0.0       // the faintest it fades to along its length, beside its strongest
#define MARBLE_YELLOW_BLUR_SHARE 0.15// how much of it blurs, 0 to 1
#define MARBLE_YELLOW_BLUR 0.5       // how much wider it is there, in pixels each way
#define MARBLE_YELLOW_BLUR_ALPHA 0.4 // and how strong, beside its sharpest

// the faintest touch of red beyond the yellow, on some of it
#define MARBLE_RED vec3(0.62, 0.25, 0.19)
#define MARBLE_RED_SHARE 0.35        // how much of the yellow has it, 0 to 1
#define MARBLE_RED_OFFSET 1.0        // beyond the yellow, in pixels
#define MARBLE_RED_DRIFT 1.0         // (further costs more)
#define MARBLE_RED_WIDTH -0.3
#define MARBLE_RED_ALPHA 0.3

// which of its texels are the stone, not inlays or carving: those of about
// the green's colour (0 to 255)
#define MARBLE_GREEN_MIN 64.0        // its green, at least
#define MARBLE_GREEN_MAX 102.0       // and at most
#define MARBLE_GREEN_MEAN 0.29       // its average brightness, 0 to 1, which the veins' own shading is relative to
