# Troubleshooting

- [Error messages in game](#error-messages-in-game)
- [Messages from the launcher and the scripts](#messages-from-the-launcher-and-the-scripts)
- [Problems in the run summary](#problems-in-the-run-summary)
- [Generator warnings](#generator-warnings)
- [Re-running a release](#re-running-a-release)
- [Players see the old pack, or no pack](#players-see-the-old-pack-or-no-pack)
- [Something is missing from the Vanilla or Lite zip](#something-is-missing-from-the-vanilla-or-lite-zip)

## Error messages in game

From MCME-Architect 3.2, `/rp release` says when it starts, sends a line as each group of zips is done, and ends with a message that says how the release went. A releaser who left the server gets that last message about 2 seconds after they next join it, under `While you were away:`, unless the server restarts first. Every line the release printed is also in MCME-Architect's log, on the server where you ran `/rp release` (see [Where the output goes](release-pipeline.md#where-the-output-goes)).

| Message | What it means | What to do |
|---|---|---|
| `Releasing <Pack> <tag> ("<title>"). …` | The release started. | Wait for the result: it comes in chat. |
| `<Pack> <tag> is released.`, or `… is released, with <n> warnings:` | Published on GitHub. The first 3 warnings follow, and where to read the rest: the dashboard's Resource packs page on the RP server, or Architect's log. | Read the warnings, then put the release live with a button of the `Put it live:` line. |
| `<Pack> <tag> is released, but its checks found …` | Published, but the pipeline wrapper's checks found errors or problems (RP server only). | Look at the run on the dashboard before you put the release live. |
| `<Pack>'s dynmap pack is built and in place.`, or `… is built and in place, with <n> warnings:` | The dynmap texture pack was rebuilt. The first 3 warnings follow, if it had any. | Nothing, unless there are warnings: read them before you rely on the pack. |
| `<Pack> <tag> failed.`, or `… failed with exit code <n>.` | The release script stopped (exit code 1), or it ended with an exit code the scripts don't use, so the script itself failed. The lines under it give its last `ERROR:` reason, and the output just before it when that reason says "above", or else its last line of output. | See [Messages from the launcher and the scripts](#messages-from-the-launcher-and-the-scripts). |
| `<Pack> <tag> didn't start: another release is running.` | Nothing was built or uploaded. The line under it says which release runs. | Wait until it has finished, then run `/rp release` again. |
| `<Pack> <tag> didn't start: the release system on this server needs an admin.` | The launcher refused: the automation folder isn't installed or its settings are invalid (exit code 2), or its ResourcePackScripts checkout isn't as GitHub has it (exit code 3). The launcher's own words follow. | An admin reads them (see [Messages from the launcher and the scripts](#messages-from-the-launcher-and-the-scripts)). |
| `<Pack> <tag> was stopped after <n> minutes, during …` | The release ran longer than the plugin allows, so the plugin stopped it and everything it started. | Check the release on GitHub, and ask an admin. A pack that needs longer can get `timeoutMinutes` in its `gitHubRpReleases` entry. |
| `<Pack> <tag> couldn't be started: …` | The script couldn't be started, usually because the automation folder in the pack's `gitHubRpReleases` entry doesn't exist. | Ask an admin to check the `path`. |
| `<Pack> can't be released from this server: …` | The pack's `gitHubRpReleases` entry lacks its owner, repo, script or path. Nothing started. | Ask an admin (see [Add a pack to the automation](server-setup.md#2-tell-mcme-architect-about-the-pack)). |
| `Releases only run on Linux servers.` | The server runs Windows. Nothing started. | Release from a Linux server. |
| `Unknown resource pack: <name>. Use one of: …` | No pack in the server's config starts with what you typed. | Use one of the names it lists. |
| `Command syntax: /rp release <rpName> <Version> <Title>` | Fewer than three arguments after `release`. | Give the pack, the tag and a title. |

### Before MCME-Architect 3.2

A server that still runs MCME-Architect 3.1 sends one message, when the script ends. It only knows whether the script ended in time and its exit code, so check the run's summary (the `Release run …` line near the end of the run, or the dashboard's Resource packs page) before you act on an error.

| Message | What it means | What to do |
|---|---|---|
| `RP release finished. You might want to do /rp server <pack> <tag>` | The script ended with exit code 0. | On the RP server, check the summary says `OK` or `OK with warnings`. Then carry on with `/rp server`. |
| `Process terminated=true exitCode=75` | Another release was running, so this one was refused. Nothing was built or uploaded. | Wait until the other release has finished, then run `/rp release` again. |
| `Process terminated=true exitCode=1` | The release script stopped. Its `ERROR:` line in Architect's log says why: an unusable tag, a tag that exists on production, a failed step. | See [Messages from the launcher and the scripts](#messages-from-the-launcher-and-the-scripts). |
| `Process terminated=true exitCode=2` | Nothing started: the automation folder isn't installed, its `automation.conf` is invalid, or the launcher couldn't run. The shell's own errors are exit code 2 too. | Read Architect's log: the launcher's lines start with `release launcher:`. Ask an admin. |
| `Process terminated=true exitCode=3` | Nothing started: the server's ResourcePackScripts checkout isn't as GitHub has it. | An admin reads the `release launcher:` line in Architect's log (see below). |
| `Process terminated=true exitCode=<other>` | The script itself failed. | Read the summary, and the run's lines in Architect's log. |
| `Process terminated=false` after 30 minutes | The release ran longer than the plugin allows, so the plugin stopped it and everything it started. Architect's log then says `The RP release script for '<Pack>' version <tag> still ran after <n> minutes, so it was stopped.` | Look for the cause in the release's lines before it. A pack that needs longer can get `timeoutMinutes` in its `gitHubRpReleases` entry. |
| `Process terminated=false exitCode=-1` straight away | The script couldn't be started, usually because the automation folder in the pack's `gitHubRpReleases` entry doesn't exist. | Ask an admin to check the `path`. |
| `Process terminated=true exitCode=-1` | The pack has no complete `gitHubRpReleases` entry (owner, repo, script and path), or the server runs on Windows. | Ask an admin to check the pack's entry (see [Add a pack to the automation](server-setup.md#2-tell-mcme-architect-about-the-pack)). |

## Messages from the launcher and the scripts

The launcher's lines start with `release launcher:`, and the release scripts' stops with `ERROR:`. MCME-Architect writes all of them to its log (see [Where the output goes](release-pipeline.md#where-the-output-goes)), and to the server console only when its `alsoServerLog` is `true`. The launcher's lines are only there: it prints them before the run starts, so a refused start leaves no run to read. It does leave a note of the refusal and its reason in `runs/refused.jsonl`, which the dashboard's Resource packs page lists for the RP server. On the RP server the scripts' lines are in the run's log too.

In the rows about a pack's checkout, `<checkout>` is the pack's folder: `<Pack>-Sodium`, `<Pack>-Vanilla`, or `<Pack>` for the dynmap pack.

| Message | Exit code | What it means | What to do |
|---|---|---|---|
| `This automation folder isn't installed` | 2 | No `automation.conf`, or no `ResourcePackScripts/` | An admin installs the folder (see [Install, check or undo](server-setup.md#install-check-or-undo)). |
| `This folder's automation.conf is invalid` | 2 | The line above it names the setting | Fix that line, or rewrite the file with `install.py --side <side> --force`. |
| `automation/automation_conf.py failed` | 2 | The settings reader itself is broken, as it is on GitHub | Fix it on GitHub. The next release picks the fix up by itself. |
| `Couldn't take the release lock` | 2 | `flock` itself failed, for example because it isn't installed. Its reason is on the line above. Another release holding the lock is a different case: exit code 75. | An admin checks that util-linux's `flock` is installed and works: `install.py --check` lists it. |
| `Permission denied` from the shell or `mkdir`, with no `release launcher:` line | 2 | `runs/` or `runs/.lock` can't be created or opened. Something was run with sudo or as root, so some files belong to another user. The git rows below can have the same cause. | An admin gives the files back to the user the Minecraft servers run as, then runs `install.py --check` as that user (see [Install, check or undo](server-setup.md#install-check-or-undo)). `install.py` itself refuses to run as root, so never use sudo with it. |
| `Someone edited ResourcePackScripts on the server` | 3 | The checkout has changes or new files. The lines after it list them as git status shows them, the first 10. | Make the change through a pull request. An admin restores the checkout: `git -C ResourcePackScripts status` shows everything that changed. If an earlier release stopped with `Couldn't bring ResourcePackScripts up to date`, these may be GitHub's own files, which that update left behind: see its row. |
| `ResourcePackScripts is on '<X>', but automation.conf says '<Y>'` | 3 | The checkout is on another branch, or on none | `git -C ResourcePackScripts switch <Y>` |
| `ResourcePackScripts has commits that GitHub's <branch> doesn't` | 3 | A commit made on the server, or GitHub's history was rewritten | Make the change through a pull request, or reset the checkout to GitHub's branch. |
| `GitHub has no branch` | 3 | `automation.conf`'s branch doesn't exist on GitHub, or was never fetched | Fix `branch`, or check that the server can reach GitHub. |
| `git can't read ResourcePackScripts` or `git status failed` | 3 | git itself fails in the checkout | An admin reads git's reason, on the line above. |
| `Couldn't bring ResourcePackScripts up to date with GitHub's <branch>` | 3 | The fast-forward itself failed, after the other checks passed: for example git can't overwrite files that belong to another user (see `Permission denied` above), or an old `.git/index.lock` is left | An admin reads git's reason, on the line above. A fast-forward that failed partway leaves some of GitHub's files behind, so the next release says someone edited the checkout. Once git's reason is fixed, check that every file `git -C ResourcePackScripts status` lists is also in `git -C ResourcePackScripts diff --stat HEAD @{upstream}`, the files the update brings. Then reset to GitHub's branch: `git -C ResourcePackScripts reset --hard @{upstream}`. |
| `ResourcePackScripts has no release script called <name>` | 2 | The launcher runs under a name that has no script in `ResourcePackScripts/automation/scripts/`: a copy of it under another name, or a script missing from the folder's branch on GitHub | Release only under the three names `install.py` writes: `releaseVanillaSodium.sh`, `releaseGeneral.sh` and `releaseDynmap.sh`, the `script:` of the pack's `gitHubRpReleases` entry. A script missing from GitHub goes back through a pull request. |
| `automation.conf asks for the pipeline wrapper, but ResourcePackScripts has no automation/pipeline/run.sh` | 2 | `wrapper=yes`, but the folder's branch on GitHub has no wrapper | Put `automation/pipeline/run.sh` back through a pull request. Until then `wrapper=no` in `automation.conf` lets releases run, without a run log or summary. |
| `Couldn't fetch '<branch>' from GitHub` | none: a warning | GitHub couldn't be reached | Nothing: the release goes on with the version fetched last. If GitHub stays unreachable, the pack's update stops the release next, with `ERROR: Couldn't fetch <checkout> from GitHub`. |
| `ERROR: The tag '…' can't be used` | 1 | The tag has characters other than letters, digits and `. _ -`, or doesn't start with a letter or digit | Use a tag like `v4.1.3`. |
| `ERROR: <tag> already exists in <owner>/<repo>, and this folder never replaces a release's zips` | 1 | A production release with a tag that exists. Nothing was built. | Use a new tag. |
| `ERROR: … holds the same files as …: the footprints textures didn't make it in` | 1 | A Footprints zip is the same as the zip it was made from. Nothing was published. | Check `Footprints/` in the automation folder. |
| `ERROR: <Pack>-Lite.zip holds the same files as <Pack>-Vanilla.zip: generateVanilla's Lite mode didn't apply, since every Lite conversion sets the shader base's MCME_LITE flag. Nothing was published.` | 1 | The Lite conversion came out as the Vanilla one. Lite always differs, even for a pack with at most two models per variant, so generateVanilla's Lite mode failed. | Report it in this repository's issues, with the run's generateVanilla lines. |
| `ERROR: Couldn't copy Footprints/…` | 1 | A footprints texture is missing, or the pack has no `assets/minecraft/textures/block/` | Check `Footprints/` and the pack. |
| `ERROR: generateVanilla stopped` | 1 | The converter failed: the lines above say why | See [Generator warnings](#generator-warnings). |
| `ERROR: Couldn't work out the release note` | 1 | A zip's `pack.mcmeta` declares no usable pack format, or `pack_formats.json` can't be read | Fix the pack's `pack.mcmeta`. |
| `ERROR: gh couldn't tell whether <tag> exists in <owner>/<repo>: …` or `ERROR: gh couldn't create the release <tag> in <owner>/<repo> (see above). Nothing was uploaded.` | 1 | GitHub refused, or couldn't be reached. Nothing was published. | Check the server's `gh` login: `gh auth status`. |
| `ERROR: gh couldn't upload every zip to the release <tag> in <owner>/<repo> (see above).`, then what to do | 1 | The release is on GitHub without all of this release's zips: `gh release create` had published it, or it existed before. The rest of the line says which: `The release existed before, so some of its zips may still be the earlier release's`, or `The release is on GitHub now, without all its zips`. | Read gh's reason above it, then do what the line says. With `replace_existing=yes`, as on the RP server, release again with the same tag: that replaces or finishes the zips. On production, which never replaces a release's zips: delete the release (`gh release delete <tag> --repo <owner>/<repo>`, or on its GitHub page), then release again, or use a new tag. |
| `ERROR: There's no <Pack>-Sodium checkout in this folder` (or `-Vanilla`) | 1 | The pack isn't set up in this automation folder | See [Check out the pack](server-setup.md#1-check-out-the-pack). |
| `ERROR: Couldn't fetch <checkout> from GitHub` | 1 | GitHub couldn't be reached, or refused the pack's repository: git's reason is on the line above. A fetch that would ask for a password, or that stalls for 60 s, gives up too. The cause can also be on the server: files in the checkout's `.git` that belong to another user, for example after a `sudo git pull`. Nothing was built. | Try again in a few minutes. If it keeps failing, an admin fixes what git's reason names: the server's access to GitHub (`git -C <checkout> fetch`), or the files' owner (see `Permission denied` above). |
| `ERROR: Someone edited <checkout> on the server` | 1 | The pack's checkout has changed or new files, which the release would zip although they aren't on GitHub. The lines above it list them as git status shows them, the first 10. Nothing was built. | An admin takes the change to the pack's repository on GitHub, or undoes it: `git -C <checkout> status` shows everything that changed. If it says a merge is in progress (`You have unmerged paths`, or `you are still merging`), an old `git pull` left it half done: `git -C <checkout> merge --abort`. If an earlier release stopped with `Couldn't bring <checkout> up to date`, these may be GitHub's own files, which that update left behind: see its row. |
| `ERROR: <checkout> has commits that GitHub's <branch> doesn't` | 1 | A commit made in the checkout on the server, or GitHub's history was rewritten. Nothing was built. | An admin takes the commits to GitHub, or resets the checkout to GitHub's branch. |
| `ERROR: <checkout> isn't on a branch` | 1 | The checkout is on no branch: a commit or tag was checked out, or an old `git pull` left a rebase half done. Nothing was built. | An admin switches it to the branch this stage builds for the pack: `development` or `master` for most packs, but not all (see [The packs in the pipeline today](pack-repository.md#the-packs-in-the-pipeline-today)). If git says a rebase is in progress, `git -C <checkout> rebase --abort` first. |
| `ERROR: <checkout> is on '<X>', which follows no branch on GitHub` | 1 | The branch was deleted on GitHub, for example a branch tried on the RP server, merged and then deleted; or it was made on the server; or it was never connected to GitHub's, or follows a branch of the checkout itself. Nothing was built. | When GitHub has `<X>`, an admin connects it: `git -C <checkout> branch --set-upstream-to=origin/<X>`. Otherwise they switch the checkout to the branch this stage builds for the pack (see [The packs in the pipeline today](pack-repository.md#the-packs-in-the-pipeline-today)). |
| `ERROR: <checkout> isn't a git checkout` | 1 | The folder has no `.git`: a copy of the pack, not a checkout. Nothing was built. | An admin checks the pack out again (see [Check out the pack](server-setup.md#1-check-out-the-pack)). |
| `ERROR: git can't read <checkout>` or `ERROR: git status failed in <checkout>` | 1 | git itself fails in the pack's checkout | An admin reads git's reason, on the line above, and repairs the checkout or checks the pack out again. |
| `ERROR: Couldn't bring <checkout> up to date with GitHub's <branch>` | 1 | The fast-forward itself failed, after the other checks passed: for example git can't overwrite files that belong to another user (see `Permission denied` above), or an old `.git/index.lock` is left | An admin reads git's reason, on the line above. A fast-forward that failed partway leaves some of GitHub's files behind, so the next release says someone edited the checkout. Once git's reason is fixed, check that every file `git -C <checkout> status` lists is also in `git -C <checkout> diff --stat HEAD @{upstream}`, the files the update brings. Then reset to GitHub's branch: `git -C <checkout> reset --hard @{upstream}`. |
| `ERROR: Start releases with the launcher` | 1 | Someone ran a script from `ResourcePackScripts/` directly: it would hold no lock | Start releases with `/rp release`, or with the launcher in the automation folder. |
| `WARNING!!! release note: the zips support different Minecraft versions` | none: a warning | The note names only the versions all the zips support | Expected after a new row in `pack_formats.json`, until the shader base's range covers it. |

**Exit code 2 is also the shell's own** for a failed redirection or a syntax error, so with exit code 2 always read Architect's log.

## Problems in the run summary

| Problem | Usual cause | What to do |
|---|---|---|
| `<zip> is empty.` | 7-Zip finished, but the zip holds no files: look at the step before it in the run. A converter that stops is not the cause: the release then ends with `ERROR: generateVanilla stopped`, and nothing is published. | Fix the cause, then release again with a new tag, or the same tag to replace the zips. |
| `7-Zip did not finish <zip>.` | Disk full, or a file vanished while zipping, for example because two releases ran at once. | Release again. |
| `<zip> has N files; the last good release (vX) had M.` | More than 10 % fewer files than last time. Either the conversion broke half-way, or the pack really lost files. | Compare with the last release. If the drop is intended (a big cleanup), ignore it. |
| `No GitHub release was created.` | `gh` couldn't create the release: no access to the release repository, GitHub down, or a bad tag. | Read the `releasing` step's output. An admin may need to check the server's GitHub login. |
| `The run stopped before it finished.` | The run was killed, usually by a server restart during the release. The next release found what it left behind. | Release again. |

## Generator warnings

A problem with one model or file is skipped with a message and the run carries on, so a release can succeed with broken blocks in it. Read them after every run. Not all of them start with `WARNING`.

On the RP server, the run's summary counts the lines that start with `WARNING!` as warnings, the release scripts' own included. Lines containing `Error` count as errors, so **one model objmc couldn't bake (`Error running process script`) makes the whole run `failed`**, even though the release went out. `Missing .mtl file`, `Missing texture for`, `Unexpected namespace` and `Note:` lines don't count at all. Search the run's log for them, or on production Architect's log.

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
| A `Traceback` | The converter stopped (see [What stops a run](conversion.md#what-stops-a-run-and-what-doesnt)). The release ends with `ERROR: generateVanilla stopped`, and nothing is published. | Fix the file named in the last lines, release again. |

Two things go wrong **without any message**:

- an `mcme:` model JSON without a `model` key;
- a missing `.obj`, for example one ignored by `.gitignore`.

Both leave the block as a missing model. Check new models in game, in the Vanilla variant.

## Re-running a release

Running `/rp release` again with a tag that already exists on GitHub:

- **On the RP server** (`replace_existing=yes`): `gh release create` fails because the tag exists (`HTTP 422`), and the summary notes "The release already existed". The line before it says that's expected: `<tag> already exists in <owner>/<repo>: its zips are replaced (replace_existing=yes). gh's 422 below is expected.` `gh release upload --clobber` then **replaces the zips** of that release.
- **On production** (`replace_existing=no`): the script stops before building anything, with `ERROR: <tag> already exists in <owner>/<repo>, and this folder never replaces a release's zips`. Use a new tag.

Replacing fixes a broken test release under the same URL. But players and servers that already have the old zip keep their copy until its SHA-1 changes, so **run `/rp server` again** for every slot that uses the tag. That stores the new SHA-1s. Using a new tag is usually simpler.

## Players see the old pack, or no pack

- **Was `/rp server` run on that server?** Each server, or each group of servers sharing a config file, needs it (see [Put the release on a server](release-pipeline.md#7-put-the-release-on-a-server)). Servers sharing a file need `/architect reload` after another one changed it.
- **Was the Minecraft version typed exactly?** A version the server doesn't know (`26.2release`) breaks the whole pack until an admin removes it (see [Fix a mistyped slot](server-setup.md#fix-a-mistyped-slot)). `/rp server` then fails without a clear message.
- **Did the SHA-1 get stored?** `/rp server` downloads every zip of the newest slot to hash it. If a zip is missing from the release, hashing stops there and the rest keep an old or empty hash. When you update an older slot, run `/rp calcsha <pack> all` afterwards.
- **Online players don't get a new release automatically.** They get it when they next join the network or walk into another RP region. `/rp <pack> -force` resends it to you, to check.
- **Is there a region for the pack where the player is?** `/rp check` tells you which pack the region at your position gives.

## Something is missing from the Vanilla or Lite zip

The converter only writes what the vanilla blockstates and items need. Check, in this order:

1. **Is the block or item in Minecraft 26.2?** The converter walks 26.2's list. Newer blocks are dropped. See [Known limits](pack-repository.md#known-limits).
2. **Is the file referenced?** Models and textures that no blockstate or item definition reaches aren't copied. `finder.py` helps find who uses a model.
3. **Is there a warning for it?** Search the run's log for the file name.
4. **Is it in a folder that is rebuilt?** `blockstates`, `items`, `models`, `textures/block` and `textures/item` are rebuilt from what is used. Everything else under `assets/` is copied as it is.
