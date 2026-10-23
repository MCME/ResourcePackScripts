// The shader base's modules a pack has turned on - lava, ice - each a define
// and its includes, for the terrain fragment shaders (mcme_modules_main.glsl
// draws them). Each pack's is written for it by ResourcePackScripts'
// generateVanilla/syncShaderBase.py, from its .mcme-shaders.json: don't edit
// it. This one, the base's own, turns none on.
// The fluid kinds each terrain pass can draw (mcme_pass.glsl): this one, the
// base's own, says every kind in every pass.
#define MCME_SOLID_KINDS 0xFFu
#define MCME_CUTOUT_KINDS 0xFFu
#define MCME_TRANSLUCENT_KINDS 0xFFu
#moj_import <minecraft:mcme_pass.glsl>
