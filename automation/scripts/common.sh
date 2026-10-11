# common.sh - what the release scripts share. Each one starts with
#
#     . "$(dirname "$0")/common.sh"
#
# The scripts run in the automation folder, started by the release launcher
# (automation/launcher.sh): it holds the release lock on descriptor 9 and
# exports this folder's settings as RP_AUTOMATION_*. MCME-Architect passes
# <pack> <owner> <repo> <tag> <title>.
#
# Staff read the output in the server console. A warning starts with
# WARNING!!!, which the wrapper counts; a stop is one ERROR: line, then exit 1.
# Exit codes 2, 3 and 75 belong to the launcher: Architect shows staff only the
# number, so the scripts never use them.

warn() {
    printf 'WARNING!!! %s\n' "$*"
}

stop() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

# Letters and digits, spelled out: a range like A-Z can match more in some locales
alnum=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789

# Safe in a path, a URL and on a command line: letters, digits and . _ -,
# starting with a letter or digit, so never an option, and never . or ..
safe_name() {
    case $1 in
    '' | [!$alnum]* | *[!$alnum._-]*) return 1 ;;
    esac
}

# Only the launcher starts a release: it takes the lock and reads automation.conf
case ${RP_AUTOMATION_REPLACE_EXISTING-} in
yes | no) replace_existing=$RP_AUTOMATION_REPLACE_EXISTING ;;
*) stop "Start releases with the launcher in the automation folder (sh $(basename "$0") <pack> <owner> <repo> <tag> <title> there), not from ResourcePackScripts: the launcher takes the release lock and reads automation.conf." ;;
esac

# The launcher wrote runs/current when it took the lock; the release is over when this script ends
trap 'rm -f runs/current' EXIT

if [ "$#" -ne 5 ]; then
    stop "$(basename "$0") takes <pack> <owner> <repo> <tag> <title>, as MCME-Architect passes them, not $# argument(s)."
fi
pack=$1
owner=$2
repo=$3
tag=$4
title=$5
safe_name "$tag" || stop "The tag '$tag' can't be used. A tag becomes part of every download URL: use only letters, digits and . _ -, starting with a letter or digit, like v4.1.3."
safe_name "$pack" || stop "The pack name '$pack' can't be used: only letters, digits and . _ -, starting with a letter or digit."
if ! safe_name "$owner" || ! safe_name "$repo"; then
    stop "The release repository '$owner/$repo' can't be used: only letters, digits and . _ -, starting with a letter or digit."
fi

# This checkout's automation/ folder, which holds the scripts' Python helpers
automation=$(cd "$(dirname "$0")/.." && pwd) || stop "Couldn't find ResourcePackScripts's automation folder."

# Does the release exist on GitHub already? gh says "release not found" when it
# doesn't; any other failure would hide the answer, so it stops the release.
# With replace_existing=no an existing release is refused before anything is
# built: production never replaces a release's zips
check_release() {
    if answer=$(gh release view "$tag" --repo "$owner/$repo" 2>&1 >/dev/null); then
        exists=yes
    elif printf '%s\n' "$answer" | grep -q 'release not found'; then
        exists=no
    else
        stop "gh couldn't tell whether $tag exists in $owner/$repo: $(printf '%s\n' "$answer" | head -n 1)"
    fi
    if [ "$exists" = yes ] && [ "$replace_existing" = no ]; then
        stop "$tag already exists in $owner/$repo, and this folder never replaces a release's zips (replace_existing=no). Use a new tag."
    fi
}

# Bring a pack checkout up to date. A failed pull carries on with the files
# already there, as releases always have (item 1 changes that); git's own error
# line marks the run in the wrapper's summary. GIT_TERMINAL_PROMPT=0: a pull
# that wants a password fails at once, and with the low speed limit one that
# stalls, under 1000 bytes/s for 60 s, gives up, instead of holding the lock
# until Architect stops the release. 9>&-: a detached `git maintenance` would
# hold the release lock after the release
pull_pack() {
    (cd "$1" && GIT_TERMINAL_PROMPT=0 GIT_HTTP_LOW_SPEED_LIMIT=1000 GIT_HTTP_LOW_SPEED_TIME=60 git pull 9>&-)
}

# release/ is the scratch folder every release builds in
fresh_release() {
    rm -rf release && mkdir release || stop "Couldn't empty release/ (see above). Nothing was published."
}

# The pack's files, without the dot files at its top (.git, .gitignore, .github)
copy_pack() {
    cp -f -r "$1"/* release || stop "Couldn't copy $1 into release/ (see above). Nothing was published."
}

# Zip release/'s contents into <zip>, next to release/; the arguments after the
# zip's name are 7z's. 7-Zip's report goes to the console, where the wrapper
# reads it. The zip an earlier release left is removed first, so a failed
# build can never publish it
zip_release() {
    zip=$1
    shift
    rm -f "$zip"
    (cd release && 7z a -y "$zip" "$@")
    case $? in
    0) ;;
    1) warn "7-Zip had a problem with some files of $zip (its report is above); they may be missing from it." ;;
    *) stop "7-Zip couldn't make $zip (its report is above). Nothing was published." ;;
    esac
    mv -f "release/$zip" "$zip" || stop "Couldn't move $zip out of release/ (see above). Nothing was published."
}

# The footprints textures, over the activator rail's in release/
footprints() {
    for texture in "$@"; do
        cp -f "Footprints/$texture" "release/assets/minecraft/textures/block/$texture" \
            || stop "Couldn't copy Footprints/$texture into the release (see above). Nothing was published."
    done
}

# must_differ <zip> <variant zip> [<why>]: a variant must hold other files
# than the zip it's compared with, or the release stops, saying why. By
# default the variant is a Footprints zip made from <zip>, and the same files
# mean the footprints textures didn't make it in. zips.py compares the files
# in them, since the zips' bytes always differ
must_differ() {
    why="the footprints textures didn't make it in"
    [ "$#" -lt 3 ] || why=$3
    python3 "$automation/zips.py" same "$1" "$2"
    case $? in
    0) stop "$2 holds the same files as $1: $why. Nothing was published." ;;
    1) ;;
    *) stop "Couldn't compare $2 with $1 (see above). Nothing was published." ;;
    esac
}

# The release note, worked out from the zips by release_note.py. Its warnings
# become WARNING!!! lines, which the wrapper counts. Without a note nothing is
# published (P7)
release_note() {
    warnings=$(mktemp) || stop "Couldn't make a temporary file for the release note. Nothing was published."
    note=$(python3 "$automation/release_note.py" "$tag" "$@" 2>"$warnings")
    status=$?
    sed 's/^release_note: warning: /WARNING!!! release note: /' "$warnings"
    rm -f "$warnings"
    if [ "$status" -ne 0 ] || [ -z "$note" ]; then
        stop "Couldn't work out the release note (see above). Nothing was published."
    fi
}

# Publish the zips as the release <tag>. With replace_existing=yes an existing
# release keeps its page and gets the new zips (--clobber): gh's "already
# exists" (HTTP 422) for the create is expected then, and the wrapper reads it
# as such, so the create still runs, after a line that says so. That line
# avoids the words the wrapper counts as errors. Only a release gh said exists
# goes on to the upload after a failed create
publish() {
    release_note "$@"
    if [ "$exists" = yes ]; then
        echo "$tag already exists in $owner/$repo: its zips are replaced (replace_existing=yes). gh's 422 below is expected."
    fi
    if ! gh release create "$tag" --repo "$owner/$repo" --title="$title" --notes="$note" && [ "$exists" != yes ]; then
        stop "gh couldn't create the release $tag in $owner/$repo (see above). Nothing was uploaded."
    fi
    set -- "$@" --repo "$owner/$repo"
    if [ "$replace_existing" = yes ]; then
        set -- "$@" --clobber
    fi
    gh release upload "$tag" "$@" || upload_failed
}

# The upload failed after the release was created, or after it was found to
# exist, so GitHub has it without all of this release's zips: say what state
# it is in, and what to do
upload_failed() {
    failed="gh couldn't upload every zip to the release $tag in $owner/$repo (see above)."
    if [ "$exists" = yes ]; then
        stop "$failed The release existed before, so some of its zips may still be the earlier release's: release again with the same tag to replace them all."
    fi
    if [ "$replace_existing" = yes ]; then
        stop "$failed The release is on GitHub now, without all its zips: release again with the same tag to finish it."
    fi
    stop "$failed The release is on GitHub now, without all its zips, and this folder never replaces a release's zips: delete the release (gh release delete $tag --repo $owner/$repo, or on its GitHub page), then release again, or use a new tag."
}
