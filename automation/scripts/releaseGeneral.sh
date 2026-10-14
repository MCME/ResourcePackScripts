#!/bin/sh
# Release a vanilla-only pack: <Pack>-Vanilla zipped as it is, and again with
# the footprints textures, published as one GitHub release with the Bedrock
# pack and Geyser's mappings that generateBedrock makes from it.
#
#     sh releaseGeneral.sh <Pack> <owner> <repo> <tag> <title>
#
# Started by the launcher in the automation folder, never directly. The lines
# "compiling <Pack> RP zips", "<Pack>-Bedrock" and "releasing <Pack> RP zips"
# are the steps the wrapper reports: keep them exactly.

. "$(dirname "$0")/common.sh"

[ -d "$pack-Vanilla" ] || stop "There's no $pack-Vanilla checkout in this folder, so $pack can't be released here."
check_release

echo "compiling $pack RP zips"
pull_pack "$pack-Vanilla"
fresh_release
copy_pack "$pack-Vanilla"
zip_release "$pack.zip" '*' '-x!inventories'
footprints activator_rail.png activator_rail_on.png
zip_release "$pack-Footprints.zip" '*' '-x!inventories'
must_differ "$pack.zip" "$pack-Footprints.zip"

echo "$pack-Bedrock"
bedrock "$pack-Vanilla"

echo "releasing $pack RP zips"
publish "$pack.zip" "$pack-Footprints.zip"
