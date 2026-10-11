#!/bin/sh
# Build the pack for the dynmap plugin: <Pack> zipped without its inventories,
# into the dynmap texture packs folder of the server next to this one. No
# GitHub release.
#
#     sh releaseDynmap.sh <Pack> <owner> <repo> <tag> <title>
#
# Started by the launcher in the automation folder, never directly. Owner,
# repo, tag and title are checked like the other scripts' but not used. The
# line "compiling <Pack> RP zips" is the step the wrapper reports: keep it
# exactly.

. "$(dirname "$0")/common.sh"

# Where dynmap reads texture packs, from this automation folder. It's there
# only where the automation folder sits in a server folder next to
# baseline-server, as on the RP server (P5)
texturepacks=../../baseline-server/plugins/dynmap/texturepacks

[ -d "$pack" ] || stop "There's no $pack checkout in this folder, so $pack can't be built here."
[ -d "$texturepacks" ] || stop "There's no dynmap texture packs folder at $texturepacks from this automation folder, so the dynmap pack can't be built here."

echo "compiling $pack RP zips"
pull_pack "$pack"
fresh_release
copy_pack "$pack"
zip_release "$pack.zip" '*' '-x!inventories'
mv -f "$pack.zip" "$texturepacks/" || stop "Couldn't move $pack.zip into $texturepacks (see above)."
