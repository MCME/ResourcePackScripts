# Fog block, waterfall spray, clouds and smoke

Experimental shaders from RP-Mordor (`experimental/fog-clouds-smoke`,
commit e0508cf2, 3 October 2026), copied here as they were, so the toolbox
holds them in one place. They predate the shared shader base, and aren't
hooked into it yet.

- **Fog block** (unconnected purple stained glass pane): drifting mist,
  traced through its block (`fog_block.glsl`, `fog_block_config.glsl`).
- **Waterfall spray** (unconnected light blue pane): thin, curling strands of
  mist, grainy like the mist texture, its grains streaming every way.
- **Clouds and smoke** as whole volumes, one block each, which the vertex
  shader spreads over the screen and the fragment shader traces once per
  pixel (`fog_volume.glsl`, `fog_volume_main.glsl`):
  - a cloud (grey pane);
  - a 40-wide smoke column, one light grey pane every 16 blocks up it,
    magenta on top;
  - chimney smoke (brown pane).

`assets/` holds the files as RP-Mordor had them: blockstates, models,
textures and shader includes.

`hooking.diff` is how that commit wired them into the terrain shaders of the
time (the vanilla and Sodium ones, and `fluid.glsl`'s fluid kinds).

## Porting it onto the shader base

- **Fluid kinds.** The base keeps kinds 5 to 7 for a pack's own fluids. RP-Mordor
  has tar at 6 (`mordor_fluid.glsl`); the fog block and the spray were 5 and 7.
- **Hooks, not copies.** Their code goes into `mcme_hook_*.glsl` (or a base
  module under `shaderBase/modules/`), using the base's `MCME_*` macros
  rather than editing `terrain.fsh`/`vsh` and `block_layer_opaque.*`. See
  `docs/shader-base.md`.
- **Signing.** Their textures need signing (`signFluids.py`) after every edit.
- **Checks.** `checkShaders.py` on a pack that uses them, and a look at the cost
  per frame: the volumes trace once per pixel over the whole screen.
