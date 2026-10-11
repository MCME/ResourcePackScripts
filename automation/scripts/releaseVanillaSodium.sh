#!/bin/sh
# Release a Sodium pack: six zips made from <Pack>-Sodium, published as one
# GitHub release. Sodium is the pack as it is; Vanilla is generateVanilla's
# conversion of it; Lite the conversion with at most two models per variant;
# and each of the three again with the footprints textures.
#
#     sh releaseVanillaSodium.sh <Pack> <owner> <repo> <tag> <title>
#
# Started by the launcher in the automation folder, never directly. The lines
# from "compiling <Pack> RP zips" through "releasing <Pack> RP zips" are the
# steps the wrapper reports: keep them exactly.

. "$(dirname "$0")/common.sh"

# The vanilla client's assets generateVanilla walks: only blocks and items in
# this version's lists reach the Vanilla and Lite zips
vanilla_assets=Vanilla-26.2

[ -d "$pack-Sodium" ] || stop "There's no $pack-Sodium checkout in this folder, so $pack can't be released here."
# Without it generateVanilla would find no blockstates, write none, and still end without an error
[ -d "$vanilla_assets" ] || stop "There's no $vanilla_assets folder here, so generateVanilla would convert nothing."
check_release

# Convert the Sodium pack into release/; the arguments are generateVanilla's
generate() {
    python3 ResourcePackScripts/generateVanilla/generateVanilla.py "$pack-Sodium" release "$vanilla_assets" \
        --objmc ResourcePackScripts/generateVanilla/objmc.py "$@" \
        || stop "generateVanilla stopped (see above), so the converted zips would be incomplete. Nothing was published."
}

echo "compiling $pack RP zips"
echo "$pack-Sodium"
pull_pack "$pack-Sodium"
fresh_release
copy_pack "$pack-Sodium"
zip_release "$pack-Sodium.zip" '-x!vanilla' '-x!.git'

echo "$pack-Sodium-Footprints"
footprints activator_rail.png
zip_release "$pack-Sodium-Footprints.zip" '-x!vanilla' '-x!.git'
must_differ "$pack-Sodium.zip" "$pack-Sodium-Footprints.zip"

# --debug only under the wrapper (it sets RP_RELEASE_RUN), which keeps those
# lines out of Architect's log and in the run's full log
echo "$pack-Vanilla"
fresh_release
generate ${RP_RELEASE_RUN:+--debug}
zip_release "$pack-Vanilla.zip" '*'

echo "$pack-Vanilla-Footprints"
footprints activator_rail.png activator_rail_on.png
zip_release "$pack-Vanilla-Footprints.zip" '*'
must_differ "$pack-Vanilla.zip" "$pack-Vanilla-Footprints.zip"

echo "$pack-Lite"
fresh_release
generate --limit 2
zip_release "$pack-Lite.zip" '*'
# generateVanilla writes the shader base's MCME_LITE flag into every Lite
# conversion, so Lite always differs from Vanilla, even for a pack with at most
# two models per variant. The same files would be Vanilla under the Lite name
must_differ "$pack-Vanilla.zip" "$pack-Lite.zip" \
    "generateVanilla's Lite mode didn't apply, since every Lite conversion sets the shader base's MCME_LITE flag"

echo "$pack-Lite-Footprints"
footprints activator_rail.png activator_rail_on.png
zip_release "$pack-Lite-Footprints.zip" '*'
must_differ "$pack-Lite.zip" "$pack-Lite-Footprints.zip"

echo "releasing $pack RP zips"
publish "$pack-Vanilla.zip" "$pack-Vanilla-Footprints.zip" "$pack-Sodium.zip" \
    "$pack-Sodium-Footprints.zip" "$pack-Lite.zip" "$pack-Lite-Footprints.zip"
