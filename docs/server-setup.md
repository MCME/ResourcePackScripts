# Add a pack to the automation

For server admins: how the server side of the pipeline is set up, how to add a pack to it, and how to change one. Pack makers need [Set up a pack repository](pack-repository.md) instead.

- [What is where](#what-is-where)
- [1. Check out the pack](#1-check-out-the-pack)
- [2. Tell MCME-Architect about the pack](#2-tell-mcme-architect-about-the-pack)
- [3. Apply the config change](#3-apply-the-config-change)
- [4. Give the pack a place in the world](#4-give-the-pack-a-place-in-the-world)
- [5. First release](#5-first-release)
- [Change a pack from vanilla-only to Sodium](#change-a-pack-from-vanilla-only-to-sodium)
- [Change the branch a stage builds](#change-the-branch-a-stage-builds)
- [Add a Minecraft version](#add-a-minecraft-version)
- [Fix a mistyped slot](#fix-a-mistyped-slot)
- [Things to know](#things-to-know)

## What is where

There are two automation folders, both called `resourcePackAutomation/`:

| | Test | Production |
|---|---|---|
| Location | inside the RP server's folder | in the network folder, next to the servers' folder |
| Used by `/rp release` on | the RP server | every other server: the shared config, hub, eventserver |
| Pack checkouts are on | `development` | `master` |
| `ResourcePackScripts/` is on | `development` | `master` |
| Pipeline wrapper (`pipeline/`, `runs/`) | Yes | No |

Each folder holds:

| Item | What it is |
|---|---|
| `releaseVanillaSodium.sh`, `releaseGeneral.sh` (and `releaseDynmap.sh` in the test folder) | The release scripts. Local files, not in any repository; keep a backup before editing one. |
| `<Pack>-Sodium/`, `<Pack>-Vanilla/` | The server's checkout of each pack. The folder name must be the pack's name exactly, capitals included, plus `-Sodium` (Sodium packs) or `-Vanilla` (vanilla-only packs). |
| `ResourcePackScripts/` | A checkout of this repository. Sodium releases pull it and run its generateVanilla. |
| `Footprints/` | `activator_rail.png` and `activator_rail_on.png`, copied into every Footprints zip |
| `Vanilla-1.21.4/` | The `assets/` of the Minecraft 1.21.4 client, which generateVanilla walks |
| `release/` | Scratch folder each release builds in. Its zips stay next to it until the next release. |
| `pipeline/`, `runs/` (test only) | The wrapper, and the log and summary of every run. Never touch `runs/.lock`: a release that finds it held refuses to start. |
| `*-Inventories/`, `*-Common/`, `*-Vanilla` of Sodium packs | Older or separate tools. Not used by the release scripts. |

The scripts publish with the `gh` command line tool, logged in on the server. That login needs write access to every release repository.

## 1. Check out the pack

In the **test** folder, check out `development`; in the **production** folder, `master`:

```bash
# Sodium pack
git clone -b development https://github.com/MCME/RP-Rivendell.git Rivendell-Sodium
# vanilla-only pack
git clone -b development https://github.com/MCME/RP-Rivendell.git Rivendell-Vanilla
```

The folder name is `<Pack>-Sodium` or `<Pack>-Vanilla`, where `<Pack>` is the name you'll use in the config, with exactly the same capitals. Every zip is named after it too.

Check that the `gh` login can create releases in the release repository:

```bash
gh api repos/<owner>/<repo> --jq .permissions.push    # must print true
```

## 2. Tell MCME-Architect about the pack

Each server's MCME-Architect `config.yml` needs two sections for the pack. Several servers share one file (see [Things to know](#things-to-know)).

### `gitHubRpReleases`: how to release it

Only needed on the servers staff release from: the RP server for test, and the shared config for production.

```yaml
gitHubRpReleases:
  Rivendell:
    owner: MCME                         # owner of the release repository
    repo: RP-Rivendell                  # the release repository
    script: releaseVanillaSodium.sh     # or releaseGeneral.sh for a vanilla-only pack
    path: <the automation folder>/      # test or production folder, see above
```

### `ServerResourcePacks`: what players get

Needed on every server whose players should get the pack. Create the empty sections, and `/rp server` fills in the slots later. **The sections must exist first.** Without the pack's section, `/rp server` answers `Error while setting server resource pack!`. Without one of its client or variant sections, it fails with an internal error and saves nothing.

For a **Sodium pack**:

```yaml
ServerResourcePacks:
  Rivendell:
    vanilla:            # the first client type is the default
      16px:
        light: {}
        footprints: {}
    sodium:
      16px:
        light: {}
        footprints: {}
    lite:
      16px:
        light: {}
        footprints: {}
```

For a **vanilla-only pack**, only the `vanilla` part.

- **The presence of `sodium` decides everything:** with it, `/rp server` writes the six names `<Pack>-Vanilla.zip`, `<Pack>-Sodium.zip`, `<Pack>-Lite.zip` and their `-Footprints`; without it, `<Pack>.zip` and `<Pack>-Footprints.zip`.
- **Order matters:** when a pack has nothing for a player's client type or variant, the first one listed is used.
- **Staff type the first letters of the pack's name.** The server takes the first pack in `ServerResourcePacks` whose name starts with what they type. Choose a name whose first letter isn't taken, or put it after the packs it clashes with.

## 3. Apply the config change

MCME-Architect keeps its config in memory, and `/rp server` writes that memory back to the file. An edited file is therefore overwritten by the next `/rp server` unless the server has read it first.

1. Edit the file.
2. **Straight away**, run `/architect reload` (console, or the permission `architect.reload`) on **every server that uses that file**. Or edit while those servers are stopped.
3. Make the first test release (step 5) to see that the server picked it up.

## 4. Give the pack a place in the world

Players get a pack through RP regions:

1. Make a WorldEdit selection of the area.
2. `/rp create <region name>` opens a chat editor.
3. In the editor, `rp <Pack>` sets the pack (the start of its name is enough, as with `/rp release`), and `weight <n>` decides which region wins where regions overlap: the highest wins.

`/rp list` lists the regions, `/rp edit <name>` changes one, and `/rp remove <name>` deletes one. Regions are per server, and show on the map in the "RpRegions" layer.

## 5. First release

On the RP server:

```
/rp release <pack> v0.1.0 First release
/rp server <pack> v0.1.0 26.2
```

Then walk into the region, or `/rp <pack> -force`, and check the pack with a vanilla client, with the modpack (`sodium`) and with `/rp client lite`.

## Change a pack from vanilla-only to Sodium

1. Check out the pack again as `<Pack>-Sodium` (the `<Pack>-Vanilla` checkout can stay until the switch is done).
2. Set `script: releaseVanillaSodium.sh` in its `gitHubRpReleases` entry.
3. Add the `sodium` and `lite` sections to its `ServerResourcePacks` entry, as above, on every config that serves the pack.
4. Apply the change (step 3 above) and make a test release.

Old slots in the `vanilla` section keep their `<Pack>.zip` URLs until `/rp server` replaces them.

## Change the branch a stage builds

```bash
cd <automation folder>/<Pack>-Sodium
git fetch
git switch <branch>
```

The next release builds that branch. The same goes for `ResourcePackScripts/`.

## Add a Minecraft version

MCME-Architect matches a player's client to a slot through its protocol table, `protocolVersions.yml` in each server's MCME-Architect folder; the active servers share one copy. It maps every slot name (`26_2`) to a protocol number (`776`).

- **Add the new version to that file before anyone runs `/rp server` for it**, then `/architect reload` on every server (or restart them). A version missing from the table breaks the pack for everyone, see [Fix a mistyped slot](#fix-a-mistyped-slot).
- **A client newer than every slot gets the newest slot.** A 26.3 client gets the `26_2` slot until the pack has a `26_3` one.

## Fix a mistyped slot

`/rp server <pack> <tag> 26.2release` saves a slot `26_2release`. Because that name isn't in the protocol table:

- the `/rp server` itself fails silently after saving;
- every later `/rp server` and plain `/rp calcsha <pack>` for that pack fails silently too (`/rp calcsha <pack> all` still works);
- **no player gets that pack** any more.

To fix it, remove the bad slot from every variant of that pack in the config file, then run `/architect reload` on every server using the file (step 3 above).

## Things to know

- **Servers share config files.** mainworld, moria, freebuild, plotworld, themedbuilds, pvpserver and terrain share one file; hub, eventserver and the RP server have their own. `/rp server` on one server rewrites the shared file from *its* memory. Run `/architect reload` on the other servers sharing it before anyone changes anything there.
- **`/rp server` refreshes the SHA-1 of the newest slot only.** It writes the URL into the slot you name but keeps that slot's old SHA-1. If you update an older slot (for example `1.21.4` while `26_2` exists), run `/rp calcsha <pack> all` afterwards, or those players' downloads fail the hash check.
- **Player URLs are stored in a 100-character database column.** `https://github.com/<owner>/<repo>/releases/download/<tag>/<zip>` must stay under 100 characters. Today's longest is 96. Keep pack names, repository names and tags short.
- **MCME-Architect waits 5 minutes** for `/rp release`, then reports `terminated=false` while the release carries on. After 10 minutes it stops waiting and reports `exitCode=-1`.
- **The production scripts differ slightly from the test ones:** no pipeline wrapper, and `releaseGeneral.sh` uploads without `--clobber`, so re-releasing a tag doesn't replace its zips there.
- **The release notes say "for MC 1.21.4"** (fixed text in the scripts).
- **generateVanilla walks `Vanilla-1.21.4`**, so blocks newer than 1.21.4 are dropped from Vanilla and Lite zips. To fix it, unzip the `assets/` of the client jar of the packs' version next to it and point the scripts at that folder. Try it on the test folder first: it changes what every Sodium release contains. **Check the folder name twice:** with a wrong vanilla folder, generateVanilla finds no blockstates, writes none, and still ends without an error.
