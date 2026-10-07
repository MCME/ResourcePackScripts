# The shader base

The shaders every MCME pack shares live once, in this repository's [`shaderBase/`](../shaderBase). [`syncShaderBase.py`](#getting-it-into-a-pack) writes them into each pack's repository, and the build adds them again. Optional **modules**, such as lava, go only to the packs that turn them on. A pack adds features of its own, such as Mordor's fire eye, through **hooks**. It never changes its copy of a base file: changed copies drift apart, and a broken copy can stop the whole pack from loading.

## What's in it

Every pack gets all of `shaderBase/assets/`:

| Files | What they do |
|---|---|
| `minecraft/shaders/core/text.vsh` | The MCME action bar |
| `minecraft/shaders/include/fog.glsl` | No fog |
| `minecraft/shaders/core/terrain.vsh`, `terrain.fsh`<br>`minecraft/shaders/include/objmc_*.glsl` | objmc: draw the baked models' real shape |
| `sodium/shaders/blocks/block_layer_opaque.*` | The same for players running the Vanilla pack with Sodium |
| `sodium/shaders/include/*.glsl` | Copies of Sodium 0.9.2's own includes (see [Sodium's includes](#sodiums-includes)) |
| `minecraft/shaders/include/fluid.glsl`, `water*.glsl` | [Water](#water), drawn by the terrain shaders. `fluid.glsl` is also what modules and a pack's own fluids build on, such as Mordor's tar. |
| `minecraft/shaders/core/lightmap.fsh`, `include/mcme_clock.glsl` | Hides the time of day in the light map, for Sodium's and Distant Horizons' terrain |
| `minecraft/shaders/include/mcme_modules.glsl`, `mcme_modules_main.glsl` | The [modules](#modules) the pack turned on, and drawing them |
| `minecraft/shaders/include/mcme_hook_*.glsl` | Empty [hooks](#hooks) |

## Modules

A module is in `shaderBase/modules/<name>/` and goes only to the packs that turn it on:

| Module | Files | Draws | On in |
|---|---|---|---|
| `lava` | `lava.glsl`, `lava_config.glsl` | `block/lava_still`, `lava_flow` | Mordor, Dwarven |
| `ice` | `ice.glsl`, `ice_config.glsl` | `block/ice` | None yet |

A pack turns modules on in a `.mcme-shaders.json` at the top of its repository. Files at the top that start with a dot never go into a zip.

```json
{
  "modules": ["lava"],
  "own": ["assets/minecraft/shaders/include/lava_config.glsl"],
  "fluids": {"powder_snow": 6}
}
```

- **`modules`**: the modules the pack gets. The sync writes them and a `mcme_modules.glsl` that turns them on.
- **`own`** (optional): base or module files the pack keeps its own version of, usually a module's settings, such as hotter lava. The sync and the build leave these alone.
- **`fluids`** (optional): the pack's own fluid textures to sign, by kind 5 to 7, such as Mordor's tar pits. The pack draws them in its hooks.

A pack without the file gets the base and no modules.

## Getting it into a pack

The release scripts on the server zip a pack's repository as it is, and they don't add the base. So the base has to be committed into every pack repository:

```
python generateVanilla/syncShaderBase.py <pack repository>
```

The sync:

- writes the base and the pack's modules, and keeps its hooks and its `own` files;
- deletes what an earlier sync wrote that the pack no longer gets, such as a module turned off, and unchanged copies of modules that are off;
- signs the pack's water, its modules' textures and its `fluids`;
- records every file it wrote, with its hash, in `.mcme-shaders.lock`;
- lists, in `pack.mcmeta`'s `sodium.ignored_shaders`, the vanilla terrain shaders and includes Sodium warns about (`terrain.vsh`, `terrain.fsh`, `fog.glsl`, `light.glsl`). Sodium doesn't run them: it runs the base's own, in the `sodium` namespace. Without the list, Sodium flags every pack with the base as incompatible. The build writes the same list into the packs it makes;
- checks that every shader import in the repository resolves.

Commit everything it changed. Run it again whenever the base changes: it does nothing when the pack is up to date.

It refuses a pack whose copy of a base file was changed by hand, because the lock no longer matches. Move the change into a hook, or list the file under `own`. For a pack's **first** sync, over copies it kept from before, check that they had no changes of its own, then run it with `--force`.

## In the build

- **Vanilla and Lite zips:** generateVanilla adds the newest base and the pack's modules to every pack it builds, over the synced copies.
- **The Lite zip** (generateVanilla with `--limit`) gets the base too, but its `mcme_lite.glsl` defines `MCME_LITE`: the terrain shaders draw no fluid, so water, lava, tar and ice show as their textures and only the models' shaders and the hooks (the fire eye) run. A pack's own shaders can check `MCME_LITE` the same way, as Mordor's Distant Horizons shaders do for their lava.
- **Sodium and vanilla-only zips** are the repository as it is, so they have the base the sync last wrote. `applyShaderBase.py` brings a copy of a pack up to the newest base, if a release script ever runs it.

Both refuse to build, and the release fails, when:

- **the pack's copy of a base or module file was changed by hand**, in `assets/` or `vanilla/assets/`. An unchanged copy of an older base is fine: the newer one replaces it.
- **a shader `#moj_import` doesn't resolve**, in any namespace. Minecraft 26.2 resolves every import in every pack shader on loading, whether the shader is used or not, and one it can't find makes it drop *all* resource packs. That's what broke the Vanilla zips of Paths of the Dead v1.8.16.
- **a shader breaks a platform rule** (see Checks): a `#version` above 410 or an `#extension` not every platform has.

## Checks

A shader one player's driver refuses drops every resource pack they have on, and nobody tests every GPU by hand. `checkShaders.py` checks a pack's shaders the ways a driver could refuse them:

```
python generateVanilla/checkShaders.py <pack> [--glslang PATH] [--fetch tested|latest]
```

- **Rules**, always, and in the build too: no `#version` above 410, because macOS stops at OpenGL 4.1, no ES shaders, and no `#extension` except `GL_ARB_separate_shader_objects`, which DH's own Blaze3D shaders need and OpenGL 4.1 has.
- **Compiling.** Every shader the pack has is compiled with its imports filled in, as the game fills them, in every define combination the game and Sodium use. glslang compiles each stage. It is the reference compiler, stricter than most drivers. With moderngl installed, each shader is also linked to the shader it runs with on a real driver: Mesa in CI, your own GPU locally.
- **Distant Horizons.** A pack's DH shader replaces DH's own of the same name outright. The check compares the two: an input, output or uniform that DH's has and the pack's lacks, or has as another type, means DH changed it since the override was written. A shader DH no longer has is never used.

The shaders a pack doesn't have, and the includes it imports from the game, come from the game's, Sodium's and DH's jars. Locally those are the ones installed in `.minecraft`. `--fetch tested` downloads the versions in `generateVanilla/shader_versions.json`, the ones the shaders were tested on in game. `--fetch latest` downloads the newest Sodium and DH for that Minecraft version, and notes every newer version of the game, Sodium, DH and Iris.

Each pack repository runs it on GitHub (`.github/workflows/check-shaders.yml`, copied from `ci/check-shaders.yml`, with the checks from this repository's `development`): on every push and pull request that touches shaders, against the tested versions; and weekly against the newest ones as well, a heads-up that never fails the repository. After testing a new version in game, raise it in `shader_versions.json`.

## Hooks

The terrain shaders import five hook files, after the water and the modules. The base's are empty. A pack overrides one by shipping its own, in its root `assets/minecraft/shaders/include/`, so that both the Sodium and the Vanilla zip get it. The same hook file serves vanilla's `terrain.*` and Sodium's `block_layer_opaque.*`.

| Hook | Where it's imported | For |
|---|---|---|
| `mcme_hook_vertex_globals.glsl` | Vertex shader, global scope, after `objmc_tools` | `out`s, imports, functions |
| `mcme_hook_vertex_main.glsl` | Vertex `main()`, after objmc, before `gl_Position` is set from `Pos` | Moving or marking faces. objmc's locals (`atlasSize`, `isCustom`, `uv`…), `UV0`, `Position` and `texCoord` are in scope. |
| `mcme_hook_vertex_end.glsl` | End of vertex `main()` | Overriding the fog distance, or `gl_Position` |
| `mcme_hook_fragment_globals.glsl` | Fragment shader, global scope, after `objmc_fragment` | `in`s, imports, functions |
| `mcme_hook_fragment_main.glsl` | Fragment `main()`, after objmc's lighting, the water and the modules, before the alpha cutout and fog | Changing `color`. `fluid` and `fluidHere` say which fluid the face is and where on it, and `shore` gives its corners' occlusion. |

Import with the namespace, `#moj_import <minecraft:my_feature.glsl>`, because Sodium's shaders are in the `sodium` namespace.

Before the hooks, the base defines these, so that a hook doesn't need to know which shader it's in:

| Macro | Vanilla | Sodium |
|---|---|---|
| `MCME_SODIUM` | not defined | defined |
| `MCME_MODELVIEW` | `ModelViewMat` | `u_ModelViewMatrix` |
| `MCME_PROJECTION` | `ProjMat`: with the view bobbing in it, so its centre is where the camera truly is | `u_ProjectionMatrix`: the same |
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

A feature every pack should have, such as water, belongs in the base itself. Its includes go in `shaderBase/`, and the base's terrain shaders import them directly, next to the hooks, so that the hooks stay free for each pack. A feature some packs want belongs in a [module](#modules): add its folder under `shaderBase/modules/`, its entry to `MODULES` in `generateVanilla/shader_base.py`, and its drawing to `mcme_modules_main.glsl` under its define.

## Water

The base draws water per pixel, fixed in the world, with one opacity as its texture had: layered ripples and crests, now and then a wave coming in from the west or north-west with a trail of foam, streaks where it flows and on falls, and, with Sodium, foam along the shores of still water. Its settings are in `water_config.glsl`.

The shaders know water by a code hidden in the lowest bits of `block/water_still.png` and `water_flow.png`. That code changes no colour by more than 3 steps in 255. The sync and the build write it into the pack's water textures (`fluid_signature.py`), and its modules' and its own fluids' the same way. A pack without its own water textures shows the game's, plain. A texture whose size isn't a multiple of 4, or with fully transparent texels, can't carry the code: the build warns and the water shows plain.

**Editing a fluid texture loses the code.** Run the sync again afterwards, or sign it by hand with `python generateVanilla/signFluids.py <pack> water` (or `lava`, `ice`).

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
