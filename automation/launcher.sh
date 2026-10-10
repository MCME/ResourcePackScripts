#!/bin/sh
# MCME release launcher.
#
# install.py puts this one file into an automation folder under every release
# script's name (releaseVanillaSodium.sh, releaseGeneral.sh, releaseDynmap.sh).
# MCME-Architect runs it as
#
#     sh <name> <Pack> <owner> <repo> <tag> <title>
#
# It takes the release lock, brings the folder's ResourcePackScripts checkout up
# to date and hands over to the script of the same name in that checkout, so the
# release scripts are never edited on the server. Change this file in the
# repository, never in an automation folder.

folder=$(cd "$(dirname "$0")" && pwd) || exit 2
cd "$folder" || exit 2
name=$(basename "$0")
checkout="$folder/ResourcePackScripts"

say() {
    printf 'release launcher: %s\n' "$*" >&2
}

setting() {
    python3 "$checkout/automation/automation_conf.py" get "$folder/automation.conf" "$1"
}

# 1. This folder's settings. The reader exits 2 when the folder isn't installed
#    or automation.conf is wrong. Any other failure is the reader itself, which a
#    fix on GitHub can't reach by itself: the launcher reads before it fetches.
branch=$(setting branch)
status=$?
if [ "$status" -eq 0 ]; then
    wrapper=$(setting wrapper)
    status=$?
fi
case $status in
0) ;;
2)
    say "This automation folder isn't installed, or its automation.conf is invalid (see above)."
    say "Install it with: python3 ResourcePackScripts/automation/install.py --side <test|production>. Or fix the line named above."
    exit 2
    ;;
*)
    say "ResourcePackScripts's automation/automation_conf.py itself failed (see above), so no release can start."
    say "If the fix is already on GitHub, update the checkout by hand: git -C ResourcePackScripts pull --ff-only"
    exit 2
    ;;
esac

# 2. The release lock, on descriptor 9. Every process that inherits the
#    descriptor holds the lock until it ends: the script and the wrapper, so the
#    lock lasts the whole release, but also anything left running in the
#    background. git may leave a detached `git maintenance` behind, so every
#    git command here runs with 9>&-.
mkdir -p "$folder/runs" || exit 2
exec 9>>"$folder/runs/.lock" || exit 2
flock -n 9
case $? in
0) ;;
1)
    running=$(cat "$folder/runs/current" 2>/dev/null)
    say "Another release is running${running:+: $running}. Start this one again once it has finished."
    exit 75
    ;;
*)
    say "Couldn't take the release lock (flock's reason is above), so no release runs here."
    exit 2
    ;;
esac
printf '%s %s (started %s)\n' "$name" "$*" "$(date '+%Y-%m-%d %H:%M:%S')" > "$folder/runs/current"

# 3. The checkout: on the declared branch, nothing edited or committed here,
#    then up to date with GitHub. Full ref names throughout, so a tag called
#    like the branch is never taken for it; symbolic-ref gives nothing on a
#    detached checkout (status 1), and git's own errors stay visible
head=$(git -C "$checkout" symbolic-ref --quiet HEAD 9>&-)
status=$?
if [ "$status" -gt 1 ]; then
    say "git can't read ResourcePackScripts (its reason is above), so no release runs here."
    exit 3
fi
if [ "$head" != "refs/heads/$branch" ]; then
    current=${head#refs/heads/}
    say "ResourcePackScripts is on '${current:-no branch}', but automation.conf says '$branch'. Switch it with: git -C ResourcePackScripts switch $branch"
    exit 3
fi
# Untracked files count too, whatever the server's git config says: a script
# dropped into the checkout must not run unreviewed
if [ -n "$(git -C "$checkout" status --porcelain --untracked-files=normal 9>&-)" ]; then
    say "Someone edited ResourcePackScripts on the server. That change must go through a pull request; until then no release runs here."
    exit 3
fi
fetched=yes
fetch_error=$(GIT_TERMINAL_PROMPT=0 git -C "$checkout" fetch --quiet origin "+refs/heads/$branch:refs/remotes/origin/$branch" 2>&1 9>&-) || fetched=no
if ! git -C "$checkout" rev-parse --verify --quiet "refs/remotes/origin/$branch" >/dev/null 9>&-; then
    say "GitHub has no branch '$branch' (or can't be reached, and it was never fetched here), so ResourcePackScripts can't follow it."
    exit 3
fi
if [ "$fetched" = no ]; then
    say "Couldn't fetch '$branch' from GitHub ($(printf '%s\n' "$fetch_error" | head -n 1)), so this release uses the version fetched last."
fi
# merge --ff-only alone would take a checkout that is ahead of GitHub as
# "already up to date", and a commit made here would go out unreviewed
if ! git -C "$checkout" merge-base --is-ancestor HEAD "refs/remotes/origin/$branch" 9>&-; then
    say "ResourcePackScripts has commits that GitHub's $branch doesn't. Either they were made on the server and need a pull request, or GitHub's history was rewritten and the checkout needs resetting to it. Until then no release runs here."
    exit 3
fi
if ! git -C "$checkout" merge --ff-only --quiet "refs/remotes/origin/$branch" >/dev/null 9>&-; then
    say "Couldn't bring ResourcePackScripts up to date with GitHub's $branch (git's reason is above)."
    exit 3
fi

# 4. Hand over with exec: the release takes this process's place, so what
#    Architect waits for and stops is the release itself, and no shell is left
#    behind (descriptor 9, and with it the lock, is inherited either way)
script="$checkout/automation/scripts/$name"
if [ ! -f "$script" ]; then
    say "ResourcePackScripts has no release script called $name."
    exit 2
fi
if [ "$wrapper" = yes ]; then
    entry="$checkout/automation/pipeline/run"
    if [ ! -f "$entry" ]; then
        say "automation.conf asks for the pipeline wrapper, but ResourcePackScripts has no automation/pipeline/run."
        exit 2
    fi
    if [ ! -x "$entry" ]; then
        say "ResourcePackScripts's automation/pipeline/run isn't executable: commit it with mode 100755 (git update-index --chmod=+x)."
        exit 2
    fi
fi
say "Releasing with ResourcePackScripts $branch at $(git -C "$checkout" rev-parse --short HEAD 9>&-)."
if [ "$wrapper" = yes ]; then
    exec "$entry" "$script" "$@"
fi
exec sh "$script" "$@"
