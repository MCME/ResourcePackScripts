# Add a pack to the automation

For server admins: how the server side of the pipeline is set up, how to add a pack to it, and how to change one. Pack makers need [Set up a pack repository](pack-repository.md) instead.

- [What is where](#what-is-where)
- [The automation folder's settings](#the-automation-folders-settings)
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
| `automation.conf` | `side=test`, `branch=development`, `replace_existing=yes`, `wrapper=yes` | `side=production`, `branch=master`, `replace_existing=no`, `wrapper=yes` |
| Release lock (`runs/.lock`) | Yes | Yes |
| Pipeline wrapper: a log and a summary of every run, in `runs/` | Yes | Yes |

Each folder holds:

| Item | What it is |
|---|---|
| `releaseVanillaSodium.sh`, `releaseGeneral.sh`, `releaseDynmap.sh` | The release launcher: three copies of one file, which `install.py` writes. **Never edit them.** The scripts they hand over to are in `ResourcePackScripts/automation/scripts/`, and a change to them goes through a pull request in this repository. |
| `automation.conf` | The folder's settings (see [The automation folder's settings](#the-automation-folders-settings)) |
| `<Pack>-Sodium/`, `<Pack>-Vanilla/` | The server's checkout of each pack. The folder name must be the pack's name exactly, capitals included, plus `-Sodium` (Sodium packs) or `-Vanilla` (vanilla-only packs). Each release brings it up to date with its branch on GitHub. **Never edit it on the server**: a release stops while the checkout has changed or new files, or commits GitHub doesn't have. |
| `ResourcePackScripts/` | A checkout of this repository, on the folder's branch. The launcher brings it up to date before every release, and runs the release scripts from it. **Never edit it on the server**: the launcher then refuses every release. |
| `Footprints/` | `activator_rail.png` and `activator_rail_on.png`, copied into every Footprints zip |
| `Vanilla-26.2/` | The `assets/` of the Minecraft 26.2 client, which generateVanilla walks |
| `release/` | Scratch folder each release builds in. Its zips stay next to it until the next release. |
| `runs/` | The release lock (`runs/.lock`; never touch it: a release that finds it held refuses to start), which release is running (`runs/current`), every refused release with why (`runs/refused.jsonl`, which the dashboard's Resource packs page lists for the RP server), and the wrapper's log and summary of every run |
| `pre-automation-backup-<stamp>/` | What `install.py` replaced, to undo the install with `--restore` |
| `*-Inventories/`, `*-Common/`, `*-Vanilla` of Sodium packs | Older or separate tools. Not used by the release scripts. |

The scripts publish with the `gh` command line tool, logged in on the server. That login needs write access to every release repository.

## The automation folder's settings

Each automation folder has an `automation.conf`, which `install.py` writes:

| Setting | Test | Production | What it decides |
|---|---|---|---|
| `side` | `test` | `production` | Which stage the folder is |
| `branch` | `development` | `master` | The branch `ResourcePackScripts/` follows |
| `replace_existing` | `yes` | `no` | Whether a release with a tag that exists replaces that release's zips. With `no` it's refused before anything is built. |
| `wrapper` | `yes` | `yes` | Whether releases go through the pipeline wrapper (a log and a summary of every run) |

Every setting is required. A setting or value the launcher doesn't know stops every release in the folder, so a typo can't change a release silently. `automation/automation.conf.example` explains the file.

### Install, check or undo

Run these in the automation folder, **as the user the Minecraft servers run as**. Never use root or sudo: files written as another user stop every release with `Permission denied`, and `install.py` refuses to run as root.

```bash
python3 ResourcePackScripts/automation/install.py --check                 # is the folder ready? changes nothing
python3 ResourcePackScripts/automation/install.py --side test             # or --side production
python3 ResourcePackScripts/automation/install.py --restore pre-automation-backup-<stamp>
```

- **Installing** writes the launcher under the three script names, and `automation.conf`. First it backs up whatever it replaces into `pre-automation-backup-<stamp>/`, then it prints the backup's name and the command that undoes the install.
  - While a release runs, it refuses with exit code 75 and changes nothing.
  - Running it again is safe: on an installed folder it changes nothing.
- **`--check`** says what stands between the folder and a working release:
  - the settings;
  - the checkout: its branch, local edits, and commits GitHub doesn't have;
  - the launchers;
  - the tools on `PATH`;
  - the lock.
- **`--restore`** puts back what an install replaced, and removes what it added.

## 1. Check out the pack

In the **test** folder, check out `development`; in the **production** folder, `master`. A few packs build other branches, or another pack's repository: when you check one of those out again, use the repository and branch that [The packs in the pipeline today](pack-repository.md#the-packs-in-the-pipeline-today) gives for it.

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

The next release builds that branch. It must follow a branch on GitHub: a release stops while the checkout's branch follows none there, for example after the branch was merged and deleted. Switch back to the branch the stage builds for that pack: `development` or `master` for most packs, but not all (see [The packs in the pipeline today](pack-repository.md#the-packs-in-the-pipeline-today)). **`ResourcePackScripts/` follows `automation.conf`:** set `branch` there, and switch the checkout with it (`git -C ResourcePackScripts switch <branch>`). The launcher refuses a checkout on another branch than the one `automation.conf` names.

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
- **MCME-Architect gives a release 30 minutes**, or `timeoutMinutes` from the pack's `gitHubRpReleases` entry. A release still running then is stopped, with everything it started, and the closing message says it was stopped (before MCME-Architect 3.2: `terminated=false`).
- **A release's output goes to MCME-Architect's log**, `plugins/MCME-Architect/logs/architect_<date>_<time>_<n>.log` on the server that ran `/rp release`. The server console gets it only with `alsoServerLog: true` in the `logging.file` section of Architect's config (see [Where the output goes](release-pipeline.md#where-the-output-goes)).
- **Both folders run the same scripts.** What differs is in `automation.conf`: production never replaces an existing release's zips, and refuses the tag before building.
- **Each launcher is a copy.** A change to `automation/launcher.sh` reaches a folder only when `install.py` runs there again. `--check` says when a copy is out of date.
- **The release note names the Minecraft versions every zip supports**, from their `pack.mcmeta` and `generateVanilla/pack_formats.json`. When Minecraft gets a new pack format, add it to that map. Until the shader base's range covers it, every Sodium release then warns that its zips support different versions, and that is expected.
- **generateVanilla walks `Vanilla-26.2`**, so blocks newer than 26.2 are dropped from Vanilla and Lite zips. To move to a newer version:
  - unzip the `assets/` of that client jar next to it;
  - change `vanilla_assets` in `automation/scripts/releaseVanillaSodium.sh` through a pull request, so the test folder gets it first.

  The script stops when that folder is missing. generateVanilla alone would find no blockstates, write none, and still end without an error.
