// The fog block's settings (fog_block.glsl). See fog_block.glsl for what it is.

#define FOG_PIXEL (1.0 / 16.0)       // its pixels' size, in blocks, as a 16px texture's

#define FOG_DENSITY 1.0              // how thick it is where it is thickest: per block of mist looked through
#define FOG_MOST 0.8                 // the most it hides, 0 to 1, so the world always shows through it
#define FOG_PATCHY 0.55              // how much of it is clear, between its wisps, 0 to 1
#define FOG_WISP 2.0                 // how big its wisps are, roughly, in blocks (a power of two)
#define FOG_SAMPLES 3                // how many times it is looked at, along the view through a block
#define FOG_SETTLE 0.4               // how much thinner it is at the top of a block than at its bottom, 0 to 1

// how it drifts: from the west, as the water's waves, in whole steps of 64
// blocks a day (0.053 blocks a second), so that it is back where it started
// when the day's clock starts over
#define FOG_DRIFT 6                  // its wisps (0.32 a second)
#define FOG_CHURN 2                  // how fast they change, against the drift

#define FOG_COLOR vec3(0.8, 0.81, 0.82)
#define FOG_TINT 0.15                // how much it takes the sky's colour, 0 to 1
#define FOG_CLEAR 1.5                // it thins out round the camera within this, in blocks

// the spray: mist thrown up where falls come down, for spray blocks (the
// unconnected light blue glass pane), stacked round a waterfall - thin
// curling strands of it and a faint haze, swept about every way by a
// turbulent flow, grainy as the mist texture is, its grains streaming along
#define SPRAY_DENSITY 1.0            // how thick its strands are to look through: per block
#define SPRAY_MOST 0.4               // the most its haze hides, 0 to 1
#define SPRAY_CURL 1.0               // how big its curls are, roughly, in blocks (a power of two)
#define SPRAY_STRAND 0.3             // how wide its strands are, 0 to 1
#define SPRAY_SWIRL 2                // how fast its flow churns and its grains stream, a whole number: 1 is about 0.4 blocks a second
#define SPRAY_GRAIN 0.7              // how grainy it is, 0 to 1
#define SPRAY_COLOR vec3(0.85, 0.88, 0.9)

// clouds, the volcano's smoke and chimney smoke: volumes, each drawn whole
// from one block (fog_volume.glsl)
#define VOLUME_STEP 1.0              // how far apart a cloud is looked at along the view, in blocks: smoke columns half as far again, chimney smoke 0.4 of it
#define VOLUME_LOOKS 12              // ...but at most this many times along each view through a volume

// a cloud: one block each - the unconnected grey glass pane - its heaps
// breaking up into separate puffs towards its edges; a few blocks together
// make a bank
#define CLOUD_SIZE 24.0              // how far its box reaches from its block, in blocks, sideways...
#define CLOUD_TALL 0.4               // ...and up and down, as a share of that
#define CLOUD_VARY 0.35              // how much clouds' sizes differ, 0 to 1
#define CLOUD_HEAP 8.0               // how big its heaps are, roughly, in blocks (a power of two)
#define CLOUD_COVER 0.5              // how much of it is clear, between its heaps, 0 to 1: more breaks it up
#define CLOUD_SWELL 0.7              // how quickly it thins out towards its box's edge
#define CLOUD_FLAT 1.8               // how much flatter it is beneath than above
#define CLOUD_EDGE 0.03              // how soft its heaps' edges are: smaller is sharper
#define CLOUD_DENSITY 2.0            // how thick it is inside its heaps: per block looked through
#define CLOUD_DRIFT 1                // how fast its heaps drift east through it, in steps of 64 blocks a day (0.053 a second)
#define CLOUD_LIT vec3(0.4, 0.38, 0.39)     // its colour where the light from above reaches...
#define CLOUD_DARK vec3(0.06, 0.055, 0.06)   // ...and where its own heaps shade it
#define CLOUD_SHADOW 2.5             // how deep its shadows are
#define CLOUD_GLOW vec3(0.45, 0.1, 0.03)     // the fires' glow on its undersides...
#define CLOUD_GLOWING 0.06           // ...and how much, 0 to 1

// the volcano's smoke column: the unconnected light grey glass pane, one
// every SMOKE_SLICE blocks straight up the column, each drawing that much of
// it; the unconnected magenta glass pane as its top slice, where it thins
// out and ends
#define SMOKE_SLICE 16               // how far apart its blocks are, up the column, in blocks
#define SMOKE_RADIUS 20.0            // its radius, about, in blocks
#define SMOKE_BILLOW 8.0             // how big its billows are, roughly, in blocks (a power of two)
#define SMOKE_COVER 0.42             // how much of it is clear, between its billows, 0 to 1
#define SMOKE_SWELL 0.45             // how quickly it thins out towards its edge
#define SMOKE_EDGE 0.06              // how soft its billows' edges are
#define SMOKE_DENSITY 0.6            // how thick it is: per block looked through
#define SMOKE_RISE 16                // how fast it rises, in steps of 64 blocks a day (0.85 a second)
#define SMOKE_ROLL 4.0               // how much its billows roll and churn as they rise, in blocks
#define SMOKE_LIT vec3(0.27, 0.25, 0.24)
#define SMOKE_DARK vec3(0.04, 0.035, 0.035)
#define SMOKE_SHADOW 3.0
#define SMOKE_GLOW vec3(0.6, 0.16, 0.04)
#define SMOKE_GLOWING 0.08

// chimney smoke: the unconnected brown glass pane - a thin plume rising from
// it, swaying more the higher it gets
#define CHIMNEY_HEIGHT 8.0           // how high it rises, in blocks
#define CHIMNEY_WIDTH 2.5            // how far its box reaches sideways, in blocks
#define CHIMNEY_BASE 0.35            // its radius where it leaves its block...
#define CHIMNEY_SPREAD 0.2           // ...and how much it widens for each block it rises
#define CHIMNEY_DENSITY 1.2          // how thick it is: per block looked through
#define CHIMNEY_RISE 24              // how fast it rises, in steps of 64 blocks a day (1.3 a second)
#define CHIMNEY_COLOR vec3(0.42, 0.4, 0.38)
