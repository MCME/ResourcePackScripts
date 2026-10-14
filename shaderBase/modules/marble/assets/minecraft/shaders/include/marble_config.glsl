// The marble's settings (marble.glsl). See marble.glsl for what it is.

#define MARBLE_PIXEL (1.0 / 16.0)    // its pixels' size, in blocks, as a 16px texture's

// the white veins: walls between cells around random points, this many cells
// per block (64 times it must be whole), only some of them veins: most of
// those running with the stone's flow, so that they join up into long veins,
// and a few across it
#define MARBLE_VEINS 1.0
#define MARBLE_SHARE_ALONG 0.97      // how many of the walls along the flow are veins, 0 to 1
#define MARBLE_SHARE_ACROSS 0.15     // and across it
#define MARBLE_FLOW_CELLS 0.25       // how quickly the flow turns: cells per block (64 times it must be whole)
#define MARBLE_JITTER 0.9            // how far the points stray from their cells' middles, 0 to 1
// how far the stone is folded before the veins are drawn, in blocks: their
// curls; then again, more finely. Too far, and it folds over on itself,
// the veins piling up
#define MARBLE_CURL 0.5
#define MARBLE_CURL_FINE 0.2
#define MARBLE_JAG 0.04              // how far they waver, finely, in blocks
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
// the branches: a finer web, every way, only near the veins
#define MARBLE_BRANCH_CELLS 3.0
#define MARBLE_BRANCH_SHARE 0.4
#define MARBLE_BRANCH_WIDTH_MAX 0.35
#define MARBLE_BRANCH_LENGTH 6.0     // how far from a vein, in pixels
#define MARBLE_BRANCH_ALPHA 0.6
// how the veins fade along their length: in patches as large as the flow's
// turns, never below this strength
#define MARBLE_FADE 0.5
// areas of more veins and fewer: this many cells per block (64 times it must
// be whole), the quietest keeping this much of the veins across the flow and
// the branches, of those along it, and of their strength
#define MARBLE_ACTIVITY_CELLS 0.25
#define MARBLE_BUSY_SHARE 0.5        // about how much of the stone is busy, 0 to 1
#define MARBLE_QUIET 0.25
#define MARBLE_QUIET_ALONG 0.85
#define MARBLE_QUIET_ALPHA 0.55

// the yellow strip roughly following the white veins, on some of them
#define MARBLE_YELLOW vec3(0.74, 0.64, 0.33)
#define MARBLE_YELLOW_SHARE 0.5      // how many of the veins have it, 0 to 1
#define MARBLE_YELLOW_OFFSET 2.0     // how far from the white's middle, in pixels, on average
#define MARBLE_YELLOW_DRIFT 2.0      // how far it strays from that, nearer or further
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
#define MARBLE_RED_DRIFT 1.5
#define MARBLE_RED_WIDTH -0.3
#define MARBLE_RED_ALPHA 0.3

// which of its texels are the stone, not inlays or carving: those of about
// the green's colour (0 to 255)
#define MARBLE_GREEN_MIN 64.0        // its green, at least
#define MARBLE_GREEN_MAX 102.0       // and at most
#define MARBLE_GREEN_MEAN 0.29       // its average brightness, 0 to 1, which the veins' own shading is relative to
