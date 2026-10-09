# Set up a pack repository

How to lay out a resource pack repository so the release pipeline can build it, both for a new pack and for an existing one. What happens to it afterwards is in [The release pipeline](release-pipeline.md).

- [First: Sodium pack or vanilla-only pack?](#first-sodium-pack-or-vanilla-only-pack)
- [Layout of a Sodium pack](#layout-of-a-sodium-pack)
- [Layout of a vanilla-only pack](#layout-of-a-vanilla-only-pack)
- [Branches](#branches)
- [.gitignore](#gitignore)
- [Try the conversion on your computer](#try-the-conversion-on-your-computer)
- [Bring a new pack into the pipeline](#bring-a-new-pack-into-the-pipeline)
- [Turn a vanilla-only pack into a Sodium pack](#turn-a-vanilla-only-pack-into-a-sodium-pack)
- [Checklist before every release](#checklist-before-every-release)
- [The packs in the pipeline today](#the-packs-in-the-pipeline-today)
- [Known limits](#known-limits)

## First: Sodium pack or vanilla-only pack?

The pipeline builds two kinds of pack:

| | Sodium pack | Vanilla-only pack |
|---|---|---|
| Has 3D `.obj` models in `assets/mcme/` | Yes | No |
| Release script | `releaseVanillaSodium.sh` | `releaseGeneral.sh` |
| Zips per release | Six: Sodium, Vanilla and Lite, each also with Footprints | Two: the pack and its Footprints copy |
| Conversion by generateVanilla | Yes, twice (Vanilla and Lite) | None, the pack is zipped as it is |
| Examples | Human, Mordor | Rohan, Lothlorien, Dwarven |

**As soon as one blockstate or item points at an `mcme:` model with an `.obj`, the pack must be a Sodium pack.** A vanilla-only release zips those models unconverted. Only players with the Special Model Loader mod can render them, so everyone else sees missing-model blocks.

## Layout of a Sodium pack

This is the layout of RP-Human and RP-Mordor, the reference packs.

```text
RP-<Name>/
├── pack.mcmeta              both variants; see below
├── pack.png                 both variants
├── license.txt              both variants
├── README.md                both variants
├── .gitignore               never in a zip
├── assets/
│   ├── minecraft/
│   │   ├── blockstates/     which model each block state uses; may point at mcme: models
│   │   ├── items/           item definitions; may point at mcme: models
│   │   ├── models/          ordinary JSON models
│   │   └── textures/
│   │   └── shaders/include/mcme_hook_*.glsl   optional: the pack's own shader features
│   └── mcme/
│       ├── models/block/    the Sodium models: <name>.json + .obj + .mtl (+ .objmeta)
│       ├── textures/block/  the textures the .mtl files name
│       └── sml_load_scopes/ Special Model Loader's list of models (Sodium variant only)
├── vanilla/                 only the Vanilla and Lite variants get this
└── 1_*/                     optional version overlays, copied as they are
```

### What ends up where

| In the repository | Sodium zip | Vanilla and Lite zips |
|---|---|---|
| `pack.mcmeta`, `pack.png`, `license.txt`, `README.md` | Yes | Yes. In `pack.mcmeta`, the word `Sodium` in the description becomes `Vanilla`. |
| Any other file at the top (`changelog.txt`, `blockList.txt`, …) | Yes | No |
| `assets/` | Yes, as it is | Rebuilt: see below |
| `vanilla/` | No | Merged in: see [The `vanilla/` folder](#the-vanilla-folder) |
| Top-level folders named `1_…` | Yes | Yes, copied as they are |
| Any other top-level folder | Yes | No |
| Anything at the top starting with a dot (`.git`, `.gitignore`, `.github`) | No | No |

**How `assets/` is rebuilt for the Vanilla and Lite zips:**
- Everything under `assets/` is copied, except the folders `blockstates`, `items`, `models`, `textures/block` and `textures/item` of every namespace, and `assets/mcme/sml_load_scopes`.
- Those folders are rebuilt from what the blockstates and item definitions actually use:
  - every `mcme:` model is baked into a vanilla model plus a texture;
  - every other model the pack overrides is copied, with its parents and textures.
- Anything nothing points at is left out. A texture in `textures/block` that only a font or GUI uses is lost, so keep such textures elsewhere, for example in `textures/gui`.

[How generateVanilla converts a pack](conversion.md) has the full details.

### pack.mcmeta

```json
{
  "pack": {
    "pack_format": 88,
    "min_format": 88,
    "max_format": 88,
    "description": "MCME Human v4.0.5 for MC 26.2"
  }
}
```

- **The pack format must match the Minecraft version the pack is for**: 88 for 26.2.
- **The description must be a plain string.** A text component (`{"text": …}`) stops generateVanilla with an error.
- **Put the version in the description**, and update it before each release. Nothing does it for you.
- **If the description contains `Sodium`**, the Vanilla and Lite variants get `Vanilla` there instead, so players can tell them apart in the pack list. Without it, all three variants show the same description.
- **Overlays:** a `1_…` folder only does something if `pack.mcmeta` lists it under `overlays`. RP-Human's `1_21_1/` isn't listed any more, so it ships without being used.

### Sodium models in `assets/mcme`

Every Sodium model is a set of files with the same name in `assets/mcme/models/block/`:

| File | Needed | What it is |
|---|---|---|
| `<name>.json` | Yes | The model in Special Model Loader's format |
| `<name>.obj` | Yes, or a shared `…_parent.obj` | The geometry, in block units (0 to 1 is one block) |
| `<name>.mtl` | Yes, unless the JSON names another one in `mtl_override`, or the `.objmeta` sets `texture` | Names the texture in a `map_Kd` line |
| `<name>.objmeta` | No | Conversion settings, see [Conversion settings](conversion.md#conversion-settings-objmeta) |

The model JSON, for example `pine_leaves.json` (shortened):

```json
{
  "parent": "special-model-loader:builtin/obj",
  "model": "mcme:models/block/leaves_parent.obj",
  "mtl_override": "mcme:models/block/pine_leaves.mtl",
  "particle": "mcme:block/beech_leaves",
  "flip_v": true
}
```

The `.mtl` it names:

```text
newmtl m_b2bff805
map_Kd mcme:block/pine_leaves
```

Rules:

- **`model` must point at an `.obj` that is committed.** A model JSON without `model`, or a missing `.obj`, is skipped **without a warning**. The block then shows as a missing model in the Vanilla and Lite variants.
- **`map_Kd` must start its line** and name a texture as `mcme:block/<texture>` (in `assets/mcme/textures/`) or `minecraft:block/<texture>` (in the pack's own `assets/minecraft/textures/`: the vanilla client's textures can't be used). Only the first `map_Kd` counts: one texture per model.
- **`model` and `mtl_override` must use the `mcme:` namespace.**
- **The texture must be at least 8 pixels wide.**
- **Textures used with one shared parent must all be the same size.** Several models can share one `.obj` named `parent` or ending in `_parent`, optionally with a number: `leaves_parent.obj`, `leaves_parent_2.obj`, `parent.obj`. The Vanilla variant then stores that geometry once. Models with differently sized textures can't share it. Read the warning `shares parent group … but its baked texture is …` as an error: fix the texture sizes. See [Shared parents](conversion.md#shared-parents).
- **Names like `leaves_vertical_slab_parent_1_2.obj` aren't shared parents** (only one number may follow `_parent`). They still work, but every model using them gets its own copy of the geometry.
- **Cutout textures (leaves, plants) should use only fully transparent and fully opaque pixels.** One semi-transparent pixel makes the whole texture render with soft edges in the Vanilla variant.
- **Animated textures** need a `.png.mcmeta` next to the texture. The sheet must divide evenly into frames, and every frame index must exist. See [Animated textures](conversion.md#animated-textures).
- **Keep `sml_load_scopes` in step with your models**, as RP-Human does. Special Model Loader reads it; the Vanilla variant leaves it out.

### Blockstates and item definitions

These live in `assets/minecraft/blockstates/` and `assets/minecraft/items/`, and point at Sodium models with an `mcme:` identifier:

```json
{
  "variants": {
    "": [
      { "model": "mcme:block/hornbeam_leaves" },
      { "model": "mcme:block/hornbeam_leaves_2" },
      { "model": "mcme:block/hornbeam_leaves_3" }
    ]
  }
}
```

- **Put the most important models first in a list.** The Lite variant keeps only the first two of every list.
- **Rotate around one axis only.** The Vanilla variant can bake an `x`, `y` *or* `z` rotation into a model, not two. With `x` and `y` on one entry, `y` is dropped with a warning. Make a pre-rotated model instead.
- **Rotations must be numbers.**
- **Only blocks and items that exist in Minecraft 1.21.4 reach the Vanilla and Lite variants** (see [Known limits](#known-limits)).

### The `vanilla/` folder

Files only the Vanilla and Lite variants need. They're merged into the converted pack's `assets/`.

- **No shaders of the base here.** The base's shaders, objmc's, `text.vsh` and `fog.glsl` among them, are in the pack's root `assets/`, written there by [the sync](shader-base.md#getting-it-into-a-pack). Don't change them: a pack with a changed copy fails to build. The pack's own shader features go into [hooks](shader-base.md#hooks).
- **`blockstates` and `items` here replace the pack's own**, for blocks that should look different without the mod.
- **`models`, `textures/block` and `textures/item` here are ignored.** Those folders are rebuilt from what the blockstates use. Old pre-baked models in `vanilla/` do nothing.
- **Everything else is copied on top**: fonts, GUI textures and so on.
- **`vanilla/1_…` folders** are merged into the overlay folders of the same name.

## Layout of a vanilla-only pack

```text
RP-<Name>/
├── pack.mcmeta
├── pack.png
├── license.txt
├── README.md
├── .gitignore
└── assets/
    └── minecraft/
        ├── blockstates/
        ├── models/
        └── textures/
```

- **Everything at the top except dot files goes into the zip, as it is.** A folder named `inventories` is left out.
- **No `mcme:` models with `.obj` files.** If you start adding them, [turn the pack into a Sodium pack](#turn-a-vanilla-only-pack-into-a-sodium-pack) first.
- **The same `pack.mcmeta` rules apply**, apart from the `Sodium` word.

## Branches

| Branch | Built by | Released to |
|---|---|---|
| `development` | Test releases on the RP server | A test repository |
| `master` | Production releases on the main servers | The pack's own repository |
| Anything else | Nothing | Nothing |

- **Work on a feature branch and open pull requests into `development`.** Several people can then work on the pack at once.
- **Bring tested work to production with a pull request from `development` into `master`.**
- **Each stage builds the branch its checkout on the server has**, whatever the pull requests say. A few packs still use older branch names (see [the table](#the-packs-in-the-pipeline-today)).

## .gitignore

Keep it short. Nothing in a pack needs ignoring except editor and OS clutter:

```gitignore
# OS and editor files
.DS_Store
Thumbs.db
desktop.ini
.idea/
.vscode/
*.bak
*.tmp
```

> [!CAUTION]
> **Never ignore `*.obj`**, and don't start from the stock Visual Studio or Python `.gitignore`. Those ignore `*.obj`, folders named `obj/`, `build/` or `release/`, and `*.meta` and `*.log` files. An ignored `.obj` never reaches GitHub, so the server builds the pack without it. That happened to a test release in October 2026: its 3D blocks showed as missing models.

Check that a file is really committed with `git check-ignore -v <file>`: it prints the rule that ignores it, or nothing.

## Try the conversion on your computer

The server runs the same converter, so a local run shows what a release will contain, with every warning, in a few minutes:

```bash
git clone https://github.com/MCME/ResourcePackScripts.git
cd ResourcePackScripts
pip install -r requirements.txt

# Vanilla variant
python generateVanilla/generateVanilla.py ../RP-Human ../out-vanilla ../minecraft-1.21.4 --objmc generateVanilla/objmc.py
# Lite variant
python generateVanilla/generateVanilla.py ../RP-Human ../out-lite ../minecraft-1.21.4 --objmc generateVanilla/objmc.py --limit 2
```

- **`../minecraft-1.21.4`** is the folder with `assets/` from the Minecraft **1.21.4** client jar (`.minecraft/versions/1.21.4/1.21.4.jar`, unzipped). Use 1.21.4 because the server does.
- **Use a new, empty output folder for every run.** The converter never deletes anything from it.
- **Read every `WARNING`, `Error`, `Missing` and `Note:` line.** Not every message starts with `WARNING`. [Troubleshooting](troubleshooting.md#generator-warnings) says what each one means.
- **To try it in game**, zip the *contents* of the output folder, so that `pack.mcmeta` is at the top of the zip, and put the zip in your `resourcepacks` folder.

## Bring a new pack into the pipeline

1. **Create the repository** under the MCME organization, as `RP-<Name>`, with `master` and `development` branches.
2. **Lay it out** as a [Sodium pack](#layout-of-a-sodium-pack) or a [vanilla-only pack](#layout-of-a-vanilla-only-pack). For a Sodium pack, start from a copy of RP-Human's `pack.mcmeta` and `license.txt`. The shaders come from [the shader base](shader-base.md): run [the sync](shader-base.md#getting-it-into-a-pack) on the new repository and commit what it wrote. **Don't copy RP-Human's `.gitignore`**: it is the stock Visual Studio one. Use the one [above](#gitignore).
3. **Check the `.gitignore`** (see [above](#gitignore)).
4. **Try the conversion locally** and fix the warnings.
5. **Ask a server admin to add the pack**, with:

   | They need | Example |
   |---|---|
   | The pack's name in the pipeline: one word, letters only. Every zip is named after it, and its first letters are what staff type. | `Rivendell` |
   | Sodium pack or vanilla-only | Sodium |
   | The repository | `MCME/RP-Rivendell` |
   | The test release repository | A test repository, or `MCME/RP-Rivendell` itself |
   | The Minecraft versions it is for | 26.2 |
   | Where players should get it | An RP region on the RP server, then the main servers |

   The admin follows [Add a pack to the automation](server-setup.md).
6. **Make the first test release** on the RP server and check it in game.

## Turn a vanilla-only pack into a Sodium pack

For a pack that so far is zipped as it is, and now gets `.obj` models.

1. **Commit the models properly.** Remove `*.obj` and similar rules from `.gitignore`, then add every `.obj`, `.mtl`, `.objmeta` and model JSON under `assets/mcme/models/block/`, and the textures under `assets/mcme/textures/`.
2. **Replace the pack's own `text.vsh`, `fog.glsl` and any objmc shaders with the shader base.** Add a `.mcme-shaders.json`, then run [the sync](shader-base.md#getting-it-into-a-pack), with `--force` the first time, and commit what it wrote.
3. **Update `pack.mcmeta`** to the right pack format. Optionally add `Sodium` to the description.
4. **List the models in `assets/mcme/sml_load_scopes/`**, like RP-Human does.
5. **Try the conversion locally.** Check that blocks only your pack has still appear in the Vanilla output. If one is missing, see [Known limits](#known-limits).
6. **Ask a server admin to switch the pack** to `releaseVanillaSodium.sh` (see [Change a pack from vanilla-only to Sodium](server-setup.md#change-a-pack-from-vanilla-only-to-sodium)). Its zips get new names: `<Pack>-Vanilla.zip` instead of `<Pack>.zip`, and so on. Its server slots get the six-zip layout at the same time.
7. **Make a test release** on the RP server and check it with the vanilla client, with the modpack, and with `/rp client lite`.

## Checklist before every release

- [ ] Everything is pushed to `development` (test) or merged into `master` (production).
- [ ] The version in `pack.mcmeta`'s description is updated.
- [ ] `git status` shows nothing left uncommitted, and no `.obj` is ignored.
- [ ] For a Sodium pack, a local conversion runs without new warnings.
- [ ] You know the new tag, and nobody else is releasing right now.

## The packs in the pipeline today

As of October 2026. The pack name is the name in the server config, with its exact capitals. Staff type its first letters.

| Pack | Type | Kind | Test (RP server): branch → release repo | Production: branch → release repo |
|---|---|---|---|---|
| Human | `h` | Sodium | `MCME/RP-Human` `development` → `EriolEandur/RP-Gondor` | `MCME/RP-Human` `master` → `MCME/RP-Human` |
| Mordor | `m` | Sodium | `MCME/RP-Mordor` `development` → `EriolEandur/RP-Mordor` | `MCME/RP-Mordor` `master` → `MCME/RP-Mordor` |
| Paths of the Dead | `p` | vanilla-only, see below | `MCME/RP-Human` `dev/PathofTheDead` → `EriolEandur/RP-Gondor`, as `Pathsofthedead` | `MCME/RP-Human` `PathOfTheDead` → `MCME/RP-Human`, as `PathsOfTheDead` |
| Dwarven | `d` | vanilla-only | `MCME/RP-Dwarven` `development` → `EriolEandur/RP-Moria` | `MCME/RP-Dwarven` `master` → `MCME/RP-Dwarven` |
| Erebor | `er` | vanilla-only | `MCME/RP-Dwarven` `erebor` → `EriolEandur/RP-Moria` | — |
| Rohan | `r` | vanilla-only | `MCME/RP-Rohan` `development` → `EriolEandur/RP-Rohan` | `MCME/RP-Rohan` `master` → `MCME/RP-Rohan` |
| Lothlorien | `l` | vanilla-only | `MCME/RP-Lothlorien` `development` → `EriolEandur/RP-Lothlorien` | `MCME/RP-Lothlorien` `master` → `MCME/RP-Lothlorien` |

`MCME/RP-PathOfTheDead` exists, but the pipeline doesn't build from it yet. Paths of the Dead is still built from RP-Human branches.

**Paths of the Dead is being turned into a Sodium pack.** Since October 2026 its test branch has `mcme:` models, but it is still released as a vanilla-only pack and its `.gitignore` ignores `*.obj`. Until it goes through [Turn a vanilla-only pack into a Sodium pack](#turn-a-vanilla-only-pack-into-a-sodium-pack), those blocks show as missing models.

## Known limits

- **Blocks newer than Minecraft 1.21.4 are dropped from the Vanilla and Lite variants.** The converter walks the block and item list of the vanilla resources it is given, and the server gives it 1.21.4's. A pack that changes copper bars or the cinnabar and sulfur blocks, for example, would lose those blockstates. The fix is on the server side: give it the resources of the version the packs are for.
- **The GitHub release notes always say "for MC 1.21.4"**, whatever the version.
- **Only one rotation axis per model entry** is baked (see [above](#blockstates-and-item-definitions)).
- **Only `1_…` overlay folders** reach the Vanilla variant. An overlay named for a newer version, such as `26_2`, would be dropped.
- **No biome tint on baked models.** The Vanilla variant strips `tintindex`, so baked grass and leaves don't take the biome colour.
- **The Sodium-Footprints zip swaps only `activator_rail.png`**, not `activator_rail_on.png` as the other Footprints zips do.
- **MCME-Architect waits 5 minutes** for a release and reports the longer ones as errors (see [Troubleshooting](troubleshooting.md#error-messages-in-game)).
