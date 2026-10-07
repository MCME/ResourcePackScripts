// The ice's settings (ice.glsl). See ice.glsl for what it is.

#define ICE_PIXEL (1.0 / 16.0)       // its pixels' size, in blocks, as a 16px texture's
#define ICE_ALPHA 0.55               // how opaque clear ice is; cracks, clouding and frost are more

// what is frozen into it, in layers, the deeper ones fainter and bluer
#define ICE_LAYERS 4                 // how many (up to 6)
#define ICE_SURFACE vec3(0.66, 0.78, 0.96)  // its colour near the surface...
#define ICE_DEEP vec3(0.4, 0.55, 0.86)      // ...and deep in it
#define ICE_CLOUD 0.55               // how cloudy it is, 0 to 1
#define ICE_BUBBLES 0.08             // how many of its small cells hold a trapped bubble, 0 to 1

// cracks frozen into it: big straight ones, finer ones between, and
// wandering fractures
#define ICE_CRACKS 0.7               // how bright the big ones are
#define ICE_CRACK_SIZE 4.0           // how far apart the big ones are, roughly, in blocks (a power of two)
#define ICE_FINE_CRACKS 0.5          // how much of the finer ones, half as far apart, is open, 0 to 1
#define ICE_FRACTURES 0.45           // how bright the wandering fractures are...
#define ICE_FRACTURE_SIZE 2.0        // ...and how far apart, roughly, in blocks (a power of two)

// frost where it meets other blocks - by their shading, as the water's shores
#define ICE_FROST 0.22               // how far it reaches, in blocks
#define ICE_FROST_COLOR vec3(0.9, 0.95, 1.0)
#define ICE_SPARKLE 0.06             // how many of the frost's pixels glint, now and then
