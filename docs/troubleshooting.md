# Troubleshooting

- [Error messages in game](#error-messages-in-game)
- [Problems in the run summary](#problems-in-the-run-summary)
- [Generator warnings](#generator-warnings)
- [Re-running a release](#re-running-a-release)
- [Players see the old pack, or no pack](#players-see-the-old-pack-or-no-pack)
- [Something is missing from the Vanilla or Lite zip](#something-is-missing-from-the-vanilla-or-lite-zip)

## Error messages in game

`/rp release` ends with one chat message. MCME-Architect only knows whether the script ended within 5 minutes and its exit code, so check the run's summary (the `Release run …` line near the end of the run, or the dashboard's Resource packs page) before you act on an error.

| Message | What it means | What to do |
|---|---|---|
| `Process terminated=false exitCode=0` | The script took longer than the plugin's 5-minute wait, then finished successfully. Every Human release does this. | Nothing. Check the summary says `OK` or `OK with warnings`, then carry on with `/rp server`. |
| `Process terminated=true exitCode=75` | Another release was running, so this one was refused. Nothing was built or uploaded. | Wait until the other release has finished, then run `/rp release` again. |
| `Process terminated=false exitCode=-1` straight away | The script couldn't be started, usually because the automation folder in the pack's `gitHubRpReleases` entry doesn't exist. | Ask an admin to check the `path`. |
| `Process terminated=false exitCode=-1` after 10 minutes | The script was still running, so the plugin stopped waiting. The release may still finish. | Watch the console or the dashboard for the run's summary. |
| `Process terminated=true exitCode=-1` | The pack has no complete `gitHubRpReleases` entry (owner, repo, script and path), or the server runs on Windows. | Ask an admin to check the pack's entry (see [Add a pack to the automation](server-setup.md#2-tell-mcme-architect-about-the-pack)). |
| `Process terminated=true exitCode=<other>` | The script itself failed. | Read the summary and the console output of the run. |
| `Command syntax: /rp release <rpName> <Version> <Title>` | Fewer than three arguments after `release`. | Give the pack, the tag and a title. |

## Problems in the run summary

| Problem | Usual cause | What to do |
|---|---|---|
| `<zip> is empty.` | The step before it failed, usually generateVanilla stopping with a Python error (look for `Traceback` in the run). | Fix the cause, then release again with a new tag, or the same tag to replace the zips. |
| `7-Zip did not finish <zip>.` | Disk full, or a file vanished while zipping, for example because two releases ran at once. | Release again. |
| `<zip> has N files; the last good release (vX) had M.` | More than 10 % fewer files than last time. Either the conversion broke half-way, or the pack really lost files. | Compare with the last release. If the drop is intended (a big cleanup), ignore it. |
| `No GitHub release was created.` | `gh` couldn't create the release: no access to the release repository, GitHub down, or a bad tag. | Read the `releasing` step's output. An admin may need to check the server's GitHub login. |
| `The run stopped before it finished.` | The run was killed, usually by a server restart during the release. The next release found what it left behind. | Release again. |
| An `error` event after `git pull` | The server's checkout couldn't be updated (conflict, unreachable GitHub). **The script went on with the old files.** | Don't use this release. An admin has to fix the checkout. |

## Generator warnings

A problem with one model or file is skipped with a message and the run carries on, so a release can succeed with broken blocks in it. Read them after every run. Not all of them start with `WARNING`.

On the RP server, the run's summary counts the lines that start with `WARNING` as warnings. Lines containing `Error` count as errors, so **one model objmc couldn't bake (`Error running process script`) makes the whole run `failed`**, even though the release went out. `Missing .mtl file`, `Missing texture for`, `Unexpected namespace` and `Note:` lines don't count at all. Search the run's console output for them.

| Message | Meaning | What to do |
|---|---|---|
| `Missing model file: …` | A blockstate, item or model names a model that neither the pack nor the vanilla client has. | Fix the name, or add the model. |
| `Expected model file not found: …` (one `!`) | An `mcme:` model is named, but its model JSON doesn't exist. The block shows as a missing model. | Add the model JSON, or fix the name in the blockstate. |
| `Missing .mtl file …` | The model's `.mtl` (its own name, or `mtl_override`) doesn't exist. Model skipped. | Add the `.mtl`, or fix `mtl_override`. |
| `Missing texture for …` | Neither the `.objmeta` nor the `.mtl` names a texture, or `map_Kd` isn't at the start of its line. Model skipped. | Add a `map_Kd` line or a `texture:` key. |
| `Error running process script` + objmc's output | objmc failed on this model: no faces, texture narrower than 8 pixels, a vertex more than 128 blocks out, a missing texture file. Model skipped. | Read objmc's message under it, fix the model or texture. |
| `Multiple rotations for …` | A blockstate entry rotates around two axes. Only the first is baked. | Make a pre-rotated model and use one rotation. |
| `Rotation … is not a number` | Model skipped. | Use a number: 90, 180, 270. |
| `… shares parent group … but its baked texture is …` | Models using one shared parent `.obj` have textures of different sizes. **Can corrupt other models' geometry** (see [Shared parents](conversion.md#shared-parents)). | Make every texture used with that `.obj` the same size. |
| `… does not divide into WxH frames - baking it unanimated` | An animated texture's sheet doesn't split evenly into frames. | Fix the sheet size, or `width` and `height` in its `.mcmeta`. |
| `Note: … lists frames past …` | The `.mcmeta` names frames the sheet doesn't have. They're dropped. | Remove them from the `.mcmeta`. |
| `Note: turning off interpolation …` | Baked animations can't interpolate. | Nothing, or remove `interpolate` from the `.mcmeta`. |
| `Unrecognised objmc bake` / `Could not find the texture in the objmc bake` | Stacking an animation's frames failed; the model is baked without animation. | Report it in this repository's issues. |
| `Unexpected texture namespace …` / `Unexpected namespace …` | A texture outside `mcme:` and `minecraft:`, or an `.obj` or `mtl_override` outside `mcme:`. | Textures: use `mcme:` or `minecraft:`. `.obj` and `.mtl`: use `mcme:`. |
| `Unrecognised texture value for …` | A model's `textures` entry has a form the tool doesn't know. Texture not copied. | Use a plain identifier or `{"sprite": …}`. |
| `Error parsing objmeta file …` | YAML error in a `.objmeta`. The defaults are used. | Fix the YAML. |
| `… leads outside the pack - skipping …` | A path or symlink points outside the pack. | Fix the pack: no links outside it. |
| `Missing assets folder` / `Missing vanilla overrides folder` | The pack has no `assets/` or no `vanilla/`. | Expected for a pack without `vanilla/`; otherwise check the path. |
| A `Traceback` | The converter stopped (see [What stops a run](conversion.md#what-stops-a-run-and-what-doesnt)). The zip is incomplete or empty. | Fix the file named in the last lines, release again. |

Two things go wrong **without any message**:

- an `mcme:` model JSON without a `model` key;
- a missing `.obj`, for example one ignored by `.gitignore`.

Both leave the block as a missing model. Check new models in game, in the Vanilla variant.

## Re-running a release

Running `/rp release` again with a tag that already exists on GitHub:

- `gh release create` fails because the tag exists (`HTTP 422`). On the RP server, the summary notes "The release already existed".
- `gh release upload --clobber` then **replaces the zips** of that release.
- **Exception: vanilla-only packs on production.** Their script uploads without `--clobber`, so the upload fails and the old zips stay. Use a new tag there.

That fixes a broken release under the same URL. But players and servers that already have the old zip keep their copy until its SHA-1 changes, so **run `/rp server` again** for every slot that uses the tag. That stores the new SHA-1s. Using a new tag is usually simpler.

## Players see the old pack, or no pack

- **Was `/rp server` run on that server?** Each server, or each group of servers sharing a config file, needs it (see [Put the release on a server](release-pipeline.md#7-put-the-release-on-a-server)). Servers sharing a file need `/architect reload` after another one changed it.
- **Was the Minecraft version typed exactly?** A version the server doesn't know (`26.2release`) breaks the whole pack until an admin removes it (see [Fix a mistyped slot](server-setup.md#fix-a-mistyped-slot)). `/rp server` then fails without a clear message.
- **Did the SHA-1 get stored?** `/rp server` downloads every zip of the newest slot to hash it. If a zip is missing from the release, hashing stops there and the rest keep an old or empty hash. When you update an older slot, run `/rp calcsha <pack> all` afterwards.
- **Online players don't get a new release automatically.** They get it when they next join the network or walk into another RP region. `/rp <pack> -force` resends it to you, to check.
- **Is there a region for the pack where the player is?** `/rp check` tells you which pack the region at your position gives.

## Something is missing from the Vanilla or Lite zip

The converter only writes what the vanilla blockstates and items need. Check, in this order:

1. **Is the block or item in Minecraft 1.21.4?** The converter walks 1.21.4's list. Newer blocks are dropped. See [Known limits](pack-repository.md#known-limits).
2. **Is the file referenced?** Models and textures that no blockstate or item definition reaches aren't copied. `finder.py` helps find who uses a model.
3. **Is there a warning for it?** Search the run's log for the file name.
4. **Is it in a folder that is rebuilt?** `blockstates`, `items`, `models`, `textures/block` and `textures/item` are rebuilt from what is used. Everything else under `assets/` is copied as it is.
