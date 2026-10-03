# The shader base

The shaders every MCME pack shares live once, in this repository's [`shaderBase/`](../shaderBase), and are added to each pack when it's built. A pack adds features of its own, such as Mordor's fire eye, through **hooks**. It never ships its own copy of a base file: copies drift apart, and a broken copy can stop the whole pack from loading.

## What's in it

| Files | What they do | Which packs get them |
|---|---|---|
| `minecraft/shaders/core/text.vsh` | The MCME action bar | Every pack |
| `minecraft/shaders/include/fog.glsl` | No fog | Every pack |
| `minecraft/shaders/core/terrain.vsh`, `terrain.fsh`<br>`minecraft/shaders/include/objmc_*.glsl` | objmc: draw the baked models' real shape | Packs with `.obj` models or hooks |
| `sodium/shaders/blocks/block_layer_opaque.*` | The same for players running the Vanilla pack with Sodium | Packs with `.obj` models or hooks |
| `sodium/shaders/include/*.glsl` | Copies of Sodium 0.9.2's own includes (see [Sodium's includes](#sodiums-includes)) | Packs with `.obj` models or hooks |
| `minecraft/shaders/include/fluid.glsl`, `water*.glsl` | [Water](#water), drawn by the terrain shaders. `fluid.glsl` is also what a pack's own fluids build on, such as Mordor's lava. | Packs with `.obj` models or hooks |
| `minecraft/shaders/core/lightmap.fsh`, `include/mcme_clock.glsl` | Hides the time of day in the light map, for Sodium's and Distant Horizons' terrain | Packs with `.obj` models or hooks |
| `minecraft/shaders/include/mcme_hook_*.glsl` | Empty [hooks](#hooks) | Packs with `.obj` models or hooks |

## How it gets into a pack

- **Vanilla and Lite zips:** generateVanilla adds the base to every pack it builds.
- **Sodium zip:** the release runs `python generateVanilla/applyShaderBase.py <copy of the pack>` before zipping. **This step still has to be added to the server's `releaseVanillaSodium.sh`.** Vanilla-only packs (`releaseGeneral.sh`) need the same step before they can drop their own `text.vsh`.

Both refuse to build, and the release fails, when:

- **the pack ships a file the base owns**, hooks aside, in `assets/` or `vanilla/assets/`. Delete the pack's copy. If it had changes of its own, move them into hooks.
- **a shader `#moj_import` doesn't resolve**, in any namespace. Minecraft 26.2 resolves every import in every pack shader on loading, whether the shader is used or not, and one it can't find makes it drop *all* resource packs. That's what broke the Vanilla zips of Paths of the Dead v1.8.16.

## Hooks

The terrain shaders import five hook files. The base's are empty. A pack overrides one by shipping its own, in its root `assets/minecraft/shaders/include/`, so that both the Sodium and the Vanilla zip get it. The same hook file serves vanilla's `terrain.*` and Sodium's `block_layer_opaque.*`.

| Hook | Where it's imported | For |
|---|---|---|
| `mcme_hook_vertex_globals.glsl` | Vertex shader, global scope, after `objmc_tools` | `out`s, imports, functions |
| `mcme_hook_vertex_main.glsl` | Vertex `main()`, after objmc, before `gl_Position` is set from `Pos` | Moving or marking faces. objmc's locals (`atlasSize`, `isCustom`, `uv`…), `UV0`, `Position` and `texCoord` are in scope. |
| `mcme_hook_vertex_end.glsl` | End of vertex `main()` | Overriding the fog distance, or `gl_Position` |
| `mcme_hook_fragment_globals.glsl` | Fragment shader, global scope, after `objmc_fragment` | `in`s, imports, functions |
| `mcme_hook_fragment_main.glsl` | Fragment `main()`, after objmc's lighting and the water, before the alpha cutout and fog | Changing `color`. `fluid` and `fluidHere` say which fluid the face is and where on it, and `shore` gives its corners' occlusion. |

Import with the namespace, `#moj_import <minecraft:my_feature.glsl>`, because Sodium's shaders are in the `sodium` namespace.

Before the hooks, the base defines these, so that a hook doesn't need to know which shader it's in:

| Macro | Vanilla | Sodium |
|---|---|---|
| `MCME_SODIUM` | not defined | defined |
| `MCME_MODELVIEW` | `ModelViewMat` | `u_ModelViewMatrix` |
| `MCME_SECONDS` (vertex) | Seconds into the day, from `GameTime` | Seconds since the region was built |
| `MCME_SECONDS` (fragment) | Seconds into the day | The same, from the light map's clock: seamless across regions |
| `MCME_WORLD_POS` | The vertex's world position | Its position within its region of 128 × 64 × 128 blocks (`MCME_REGION`) |
| `MCME_WORLD_POS_64` | The vertex's world position mod 64 blocks | The same, exactly: Sodium's regions lie on that grid. For patterns that must look identical with and without Sodium. |
| `MCME_SECTION_CENTRE` | The section's centre, relative to the camera | The same |
| `MCME_FOG_DISTANCE(p)` | Fogs the vertex as if it were at `p` | The same (nothing without fog) |
| `MCME_TEXCOORD` (fragment) | The fragment's atlas coordinate (`texCoord`) | The same (`v_TexCoord`) |
| `MCME_ATLAS_SIZE` (fragment) | The block atlas's size in texels | The same |
| `MCME_FOG_START` (fragment) | Where the render-distance fog starts | The same |
| `MCME_FOG_COLOR` (fragment) | The fog's colour, a `vec4` | The same |

For example, Mordor's fire eye as hooks:

```glsl
// mcme_hook_vertex_main.glsl
#define FIRE_MODELVIEW MCME_MODELVIEW
#define FIRE_SECONDS MCME_SECONDS
#moj_import <minecraft:fire_eye_main.glsl>

// mcme_hook_vertex_end.glsl: fog the eye as one thing, at its centre
if (fireLayer >= 0) {
    MCME_FOG_DISTANCE(fireCentre);
}
```

Shaders a feature adds that the base doesn't have, such as Mordor's `sky.fsh`, or Distant Horizons' shaders, simply stay in the pack.

A feature every pack should have, such as water, belongs in the base itself. Its includes go in `shaderBase/`, and the base's terrain shaders import them directly, next to the hooks, so that the hooks stay free for each pack.

## Water

The base draws water per pixel, fixed in the world: layered ripples, see-through looking down, the sky's colour at a glance, and foam where it flows, on falls and, with Sodium, along shores. Its settings are in `water_config.glsl`.

The shaders know water by a code hidden in the lowest bits of `block/water_still.png` and `water_flow.png`. That code changes no colour by more than 3 steps in 255. The build writes it into every pack's water textures (`fluid_signature.py`), so packs don't have to. A pack without its own water textures shows the game's, plain. A texture whose size isn't a multiple of 4, or with fully transparent texels, can't carry the code: the build warns and the water shows plain.

To see the water while working on a pack without building it, sign the pack's water textures once with `python generateVanilla/signFluids.py <pack> water`. A pack's own fluids are signed the same way, such as Mordor's lava with `lava`, again after every edit of the textures.

## Working on shaders without building

`shaderBase/` is a resource pack itself. To see shader changes straight away, on vanilla or with Sodium:

1. Link it into your `resourcepacks` folder. On Windows, in `cmd`:
   ```bat
   mklink /J "%APPDATA%\.minecraft\resourcepacks\MCME-shaderBase" "C:\path\to\ResourcePackScripts\shaderBase"
   ```
   Link your pack checkout the same way.
2. In the game, put the pack **above** `MCME-shaderBase`.
3. Edit the base or your hooks, then press F3 + T.

On Sodium, the pack's `.obj` models render through Special Model Loader, and its hooks run in Sodium's terrain shader. On vanilla, the pack's `.obj` models don't show until it's built, but its hooks do.

## Changing the base

- **Test with glslang** (or in game) on vanilla, with Sodium, and with `ALPHA_CUTOUT`.
- **objmc changes:** the base's `objmc_*.glsl` must match this repository's `objmc.py`. Change both in the same pull request.
- **Sodium updates:** `block_layer_opaque.*` is Sodium's own shader with objmc and the hooks added. Compare it with the new Sodium jar's `assets/sodium/shaders/` and re-copy the four includes.

### Sodium's includes

Sodium compiles its shaders through Minecraft's own preprocessor, which only expands `#moj_import`. So `block_layer_opaque.*` has to import `<sodium:globals.glsl>` and so on, just like Sodium's originals. Without Sodium those files don't exist, and Minecraft would drop the pack. So the base ships copies of them.

Writing `#include` instead loads without Sodium, but breaks the shader *with* Sodium.
