# The Bedrock pack

Every release also makes a Bedrock version of the pack, for players who join on Bedrock Edition through [Geyser](https://geysermc.org). **generateBedrock** in this repository does the conversion. It works like GeyserMC's own converter [Rainbow](https://github.com/GeyserMC/rainbow), but it runs on the release server from the pack's files, without a game client, and it also converts MCME's `.obj` models.

- [What a release makes](#what-a-release-makes)
- [Put it on a Geyser server](#put-it-on-a-geyser-server)
- [How a pack becomes a Bedrock pack](#how-a-pack-becomes-a-bedrock-pack)
- [The `.obj` models: cubes and poly_mesh](#the-obj-models-cubes-and-poly_mesh)
- [What Bedrock shows differently](#what-bedrock-shows-differently)
- [Settings: `.mcme-bedrock.json`](#settings-mcme-bedrockjson)
- [Run it on your computer](#run-it-on-your-computer)
- [Checking a conversion in game](#checking-a-conversion-in-game)
- [Warnings](#warnings)
- [What isn't known yet](#what-isnt-known-yet)
- [A new Minecraft version](#a-new-minecraft-version)

## What a release makes

Two more files in every GitHub release, next to the zips:

| File | What it is | Where it goes |
|---|---|---|
| `<Pack>-Bedrock.mcpack` | The Bedrock resource pack: block geometry, textures, `terrain_texture.json` | Geyser's `packs/` folder |
| `<Pack>-Geyser.json` | Geyser's block mappings: for each Java block state the pack changes, the Bedrock custom block that draws it | Geyser's `custom_mappings/` folder |

Both come from the same checkout as the Java zips: `<Pack>-Sodium` for a Sodium pack (with its `.obj` models), `<Pack>-Vanilla` for a vanilla-only pack. The `vanilla/` folder and the version overlays are left out: they exist for objmc and for newer Java versions, which Bedrock doesn't need.

**The Bedrock step never stops a release.** If generateBedrock stops, or the pack turns it off, the release goes ahead with the Java zips and without the Bedrock files, with a `WARNING!!!` line that says so. Only a 7-Zip failure stops it, as for every zip.

## Put it on a Geyser server

1. In Geyser's `config.yml`, `enable-custom-content` must be `true`.
2. Copy `<Pack>-Geyser.json` into Geyser's `custom_mappings/` folder and `<Pack>-Bedrock.mcpack` into its `packs/` folder. Remove the previous release's two files: two mappings files for the same Java blocks conflict.
3. Restart the server. Geyser reads both only when it starts.

Bedrock players then download the pack when they join, and see the pack's blocks.

> [!IMPORTANT]
> **One pack per Geyser.** Java players switch packs as they walk between RP regions. Bedrock has no such switch: Geyser registers its custom blocks once, when it starts, and a Bedrock client gets its packs when it joins. Each server, or each Geyser on a proxy, offers one MCME pack to Bedrock players: pick the one for the area that server hosts.

> [!NOTE]
> **Biome tint needs a small Geyser change.** The mappings ask Bedrock to tint grass and foliage by biome (`tint_method`), and Geyser's API and core pass that on to the client, but its mappings reader doesn't read the field yet. `generateBedrock/tools/geyser-tint-method.patch` adds the seven lines it needs. Until a Geyser with them runs, tinted faces show their grey texture, unless the pack bakes its tints (`"tint": "baked"`, see [Settings](#settings-mcme-bedrockjson)).

## How a pack becomes a Bedrock pack

**Which blocks.** Every Java block whose drawing the pack changes: with its blockstate file, a model anywhere in a model's parent chain, or a texture. Each of its states that the client draws from a model gets a custom block of its own in the mappings. Blocks the pack leaves as they are stay Bedrock's own blocks, and so do states the client doesn't draw from a model, such as fluids. A blockstate file that only repeats vanilla's changes nothing.

**What each state gets.** The geometry and materials its models draw, and what Bedrock needs to know about the block that a resource pack can't say: how much light it gives and lets through (Bedrock lights the world on the client) and its friction. These come from the game itself, `generateBedrock/java_blocks.json` (see [A new Minecraft version](#a-new-minecraft-version)). Geyser takes the collision and selection boxes from the Java block on its own.

**Geometry.** A state that is one whole cube with a plain texture on each side uses Bedrock's own full block, which Bedrock leaves out against its neighbours like a vanilla block. Anything else gets a geometry file:

- A JSON model's element stays one cube. A blockstate's quarter turns are applied to the cube itself, with `uvlock` as Java does it, so the cube stays on the grid. An element's own `rotation`, such as a 22.5° or 45° plant, turns the cube.
- An `.obj` model: see [the next section](#the-obj-models-cubes-and-poly_mesh).

States whose models differ only in texture share one geometry file, so a pack with 20,000 converted states has about 2,500 of them.

**Textures.** Every texture a converted state uses goes into the pack, the pack's own and vanilla's alike, under `textures/java/`. The render method follows the texture, as Java's does: opaque, cut out (any fully clear pixel) or blended (any half-clear pixel). An animated texture becomes a flipbook.

**Tints.** A face Java tints by biome, like grass and most leaves, asks Bedrock for the same biome tint (see the note above). A tint that doesn't depend on the biome, such as redstone wire's, is multiplied into a copy of the texture.

## The `.obj` models: cubes and poly_mesh

Bedrock can't read an `.obj`. Its block geometry is made of cubes, and of a bone's `poly_mesh`, a list of polygons. generateBedrock draws each face of an `.obj` the way that reproduces it exactly:

- **A rectangle whose texture is a rectangle** becomes a cube of no thickness, turned to lie where the face lies. This is exact, and every Bedrock version draws it. About 80 % of the faces in MCME's `.obj` models are such rectangles, and two triangles that make up one become one too.
- **Any other face**, a triangle or a quad of another shape, goes into the `poly_mesh`. A triangle is written as a quad that repeats its first corner, as in the example meshes Bedrock is known to draw: Bedrock draws a poly_mesh's quads only.

`"geometry"` in the pack's [settings](#settings-mcme-bedrockjson) changes this: `"polymesh"` puts every `.obj` face in the poly_mesh, and `"cubes"` uses no poly_mesh at all and draws each odd face as the rectangle around it.

**Models beyond the block.** Like Java with Special Model Loader, Bedrock gets each `.obj` model whole, however far it reaches outside its block (`"oversize": "keep"`). Mojang documents a limit of 30 × 30 × 30 pixels for a block's geometry, with the block's own cell, and Blockbench's block format keeps models to it; whether Bedrock holds every block to it, and a poly_mesh too, is one of the [things to check in game](#what-isnt-known-yet). `"oversize": "polymesh"` puts every face of such a model in the poly_mesh, and `"clip"` leaves out the faces outside the largest box that fits.

## What Bedrock shows differently

| Java | On Bedrock | Why |
|---|---|---|
| A blockstate entry with several models, picked at random per position | The first model of each list | A Bedrock block state has one look. The Lite variant keeps the first entries too. |
| An `.obj` with several materials | The `.mtl`'s first texture on every face | As for the Vanilla variant |
| Faces left out against a full neighbour (`cullface`) | Drawn, except for full blocks | Bedrock leaves out neighbouring faces only of its full block |
| Blocks drawn by the client itself: signs, chests, beds, banners | Bedrock's own | Their models have no elements to convert |
| Items, armour, entities | Bedrock's own | The conversion handles blocks only, so far |
| Biome tint | Grey until Geyser reads `tint_method`, or a fixed colour with `"tint": "baked"` | See [Put it on a Geyser server](#put-it-on-a-geyser-server) |
| RP regions | One pack per Geyser | See [Put it on a Geyser server](#put-it-on-a-geyser-server) |

Bedrock keeps a pack it has downloaded until the pack's version changes. The version comes from the release tag (`v4.1.3` is 4.1.3), so a tag used again on the RP server leaves Bedrock players with what they had: use a new tag to test a Bedrock change.

## Settings: `.mcme-bedrock.json`

A pack can change how it's converted with a `.mcme-bedrock.json` at the top of its repository. It starts with a dot, so it's never zipped. Every key is optional:

```json
{
  "enabled": true,
  "name": "MCME Human",
  "geometry": "hybrid",
  "oversize": "keep",
  "tint": "biome",
  "baked_colours": {"grass": "#91bd59", "foliage": "#77ab2f"},
  "reverse_polymesh_winding": false
}
```

| Key | Default | Effect |
|---|---|---|
| `enabled` | `true` | `false`: no Bedrock files for this pack |
| `name` | `MCME <Pack>` | The pack's name in Bedrock's pack list |
| `geometry` | `hybrid` | `.obj` faces: `hybrid` (rectangles as cubes, the rest as poly_mesh), `polymesh` (all as poly_mesh) or `cubes` (no poly_mesh) |
| `oversize` | `keep` | A model larger than 30 × 30 × 30 pixels: `keep` it whole, put it all in the `polymesh`, or `clip` it |
| `tint` | `biome` | `biome`: tint by biome (`tint_method`). `baked`: multiply a fixed colour into the texture |
| `baked_colours` | plains | The colours `baked` uses: `grass`, `foliage`, `birch_foliage`, `evergreen_foliage`, `dry_foliage`, `water`, as `#rrggbb` |
| `reverse_polymesh_winding` | `false` | Turns every poly_mesh polygon round. Only if the [check in game](#checking-a-conversion-in-game) shows them from the wrong side |

A key that can't be used is reported with a warning and its default kept: a typo never stops a release.

## Run it on your computer

```bash
python generateBedrock/generateBedrock.py <pack> <output folder> <vanilla resources> --name Human --tag v4.1.3 \
    --mappings Human-Geyser.json --mcpack Human-Bedrock.mcpack
```

- `<pack>` is the pack's checkout (for a Sodium pack, its Sodium variant), `<vanilla resources>` the unzipped client jar's folder that holds `assets/`, as for generateVanilla.
- The output folder becomes the pack itself; `--mcpack` also zips it. Use a new, empty folder every time.
- `--geometry` and `--tint` override the pack's settings for one run.

It takes a minute or two: Human about 1½ minutes on a desktop.

## Checking a conversion in game

Bedrock's handling of geometry is barely documented, so the conversion comes with a test add-on that shows what Bedrock makes of it, without a server or Geyser:

```bash
python generateBedrock/tools/testAddon.py MCME-Bedrock-test.mcaddon --vanilla <vanilla resources> \
    --pack Human=<RP-Human checkout> --pack Mordor=<RP-Mordor checkout>
```

Open the `.mcaddon` on a computer with Minecraft Bedrock, make a Creative world with both of its packs, and turn on the Content Log (Settings, Creator) to see what Bedrock refuses. Every case is a block in the Construction tab named "MCME test: …", in several versions to compare side by side:

| Case | What it should look like |
|---|---|
| compass full block, compass inset cube | Each side shows its own direction's letter, readable from outside: from the south you read S, from above U. A yellow square sits in each texture's top-left corner. |
| plaque (hybrid), plaque (polymesh) | The same purple tile with an upright F, turned about all three axes. The two must look the same. |
| triangle facing south | A purple triangle with an F, seen from the south side only |
| goblin chandelier, catwalk 45, white tree canopy | As on Java, reaching well beyond their block. Compare `hybrid`, `polymesh` and `clipped`. |
| spiked log, beech branch, animal skull, apple leaves | As on Java; `polymesh` and `cubes` versions to compare |
| oak leaves (hybrid), (baked tint) | Green by biome, and a fixed green |
| oak stairs uvlock, no uvlock | Upside-down stairs, turned. With uvlock the planks' grain lies as on the blocks around them, without it the grain turns with the stairs: compare with the same blocks on Java |

## Warnings

All of generateBedrock's lines start with `Bedrock:`, so in a release they can't be mistaken for the Java steps'. Like generateVanilla's, a warning skips one model or state and never stops the run.

| Warning | Meaning |
|---|---|
| `Missing model file: …` / `Missing texture file: …` | A model or texture is named that neither the pack nor vanilla has. Java draws such a texture purple and black; Bedrock keeps its own block for those states. Fix the name in the pack. |
| `Missing .obj file for …` | The model's `model` names an `.obj` that isn't there |
| `… names an .obj outside the mcme namespace` | `.obj` files are read from `assets/mcme` only |
| `N .obj model(s) use several materials …` | Only the first texture of each is drawn, as for the Vanilla variant |
| `… is animated with frames of WxH …` | Bedrock animates square frames only, so the texture shows its first frame |
| `.mcme-bedrock.json: …` | A setting that can't be used; its default is kept |

These lines are information, not warnings:

| Line | Meaning |
|---|---|
| `Bedrock: N block(s), N state(s), N geometries …` | What the pack converted to |
| `… blockstate entries list several models …` | Bedrock draws the first of each (see [What Bedrock shows differently](#what-bedrock-shows-differently)) |
| `… material(s) are tinted by biome (tint_method) …` | See the note under [Put it on a Geyser server](#put-it-on-a-geyser-server) |
| `… model(s) reach beyond the 30x30x30 pixels …` | Kept whole (`"oversize": "keep"`) |

## What isn't known yet

What Bedrock does with some of this isn't documented. [The test add-on](#checking-a-conversion-in-game) answers these, and the defaults above may change with the answers:

| Question | Default until then |
|---|---|
| Does a custom block draw a `poly_mesh` at all? Mojang's geometry reference calls `poly_mesh` deprecated, and Bedrock has been known to draw it on entities only. | `hybrid`: only the faces no cube can draw are in the poly_mesh |
| Does Bedrock draw block geometry beyond 30 × 30 × 30 pixels, as cubes or as a poly_mesh? | `keep` |
| Which side of a `poly_mesh` polygon is its front? The example meshes say the side the face's corners turn counter-clockwise on, before x is mirrored. | `reverse_polymesh_winding: false` |
| Does a Geyser with the patch tint by biome? | `biome` |

## A new Minecraft version

The release server converts Minecraft 26.2's blocks (`Vanilla-26.2`). For another version, `generateBedrock/java_blocks.json` has to come from that version's game: its blocks, their states, and their light. `generateBedrock/tools/DumpBlockStates.java` writes it from the server jar, which isn't obfuscated since 26.1:

1. Download that version's `server.jar` and start it once with `java -DbundlerMainClass=net.minecraft.data.Main -jar server.jar --reports` in an empty folder. It unpacks itself into `versions/` and `libraries/`.
2. Compile and run the dumper there, with every jar on the class path (`;` instead of `:` on Windows):

   ```bash
   CP="versions/<version>/server-<version>.jar:$(find libraries -name '*.jar' | tr '\n' ':')"
   javac -d dump -cp "$CP" DumpBlockStates.java
   java -cp "dump:$CP" DumpBlockStates java_blocks.json
   ```

3. Replace `generateBedrock/java_blocks.json` with the new file. It has one block per line, so its diff shows what the version changed.
