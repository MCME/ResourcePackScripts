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
# to date, reads the folder's automation.conf with the reader it just updated,
# and hands over to the script of the same name in that checkout, so the
# release scripts are never edited on the server. Change this file in the
# repository, never in an automation folder: each folder has a copy, which
# install.py replaces.
#
# Its own exit codes: 2 the folder isn't installed or can't release, 3 the
# checkout isn't as GitHub has it, 75 another release holds the lock. Any
# other code is the release's own.

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

# The checkout must be on the branch the folder follows ($1, when known)
wrong_branch() {
    say "ResourcePackScripts is on '${current:-no branch}', but automation.conf says '${1:-?}'. Switch it with: git -C ResourcePackScripts switch ${1:-<branch>}"
    exit 3
}

# 1. An installed folder. Its settings are read only once the checkout is up
#    to date (step 4), so that a fix to the reader on GitHub reaches this
#    folder by itself
if [ ! -f "$folder/automation.conf" ] || [ ! -e "$checkout/.git" ]; then
    say "This automation folder isn't installed: it has no automation.conf, or no ResourcePackScripts checkout."
    say "Install it with: python3 ResourcePackScripts/automation/install.py --side <test|production>"
    exit 2
fi

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
    # With the wrapper, its own refusal: it says which release runs and notes
    # the attempt for the dashboard (runs/refused.jsonl)
    if [ "$(setting wrapper 2>/dev/null)" = yes ] && [ -f "$checkout/automation/pipeline/rp-release.py" ]; then
        python3 "$checkout/automation/pipeline/rp-release.py" refused --runs runs --script "$name" \
            --server-log "${RP_SERVER_LOG:-../logs/latest.log}" -- "$@" 9>&- && exit 75
    fi
    running=$(cat "$folder/runs/current" 2>/dev/null)
    say "Another release is running${running:+: $running}. Start this one again once it has finished."
    exit 75
    ;;
*)
    say "Couldn't take the release lock (flock's reason is above), so no release runs here."
    exit 2
    ;;
esac
# Which release holds the lock, for one refused meanwhile. The release script
# removes it when it ends, and this launcher when it stops before the hand-over
printf '%s %s (started %s)\n' "$name" "$*" "$(date '+%Y-%m-%d %H:%M:%S')" > "$folder/runs/current"
trap 'rm -f "$folder/runs/current"' EXIT

# 3. The checkout, on the branch it is on: nothing edited or committed here,
#    then up to date with GitHub. Full ref names throughout, so a tag called
#    like the branch is never taken for it; symbolic-ref gives nothing on a
#    detached checkout (status 1), and git's own errors stay visible
head=$(git -C "$checkout" symbolic-ref --quiet HEAD 9>&-)
status=$?
if [ "$status" -gt 1 ]; then
    say "git can't read ResourcePackScripts (its reason is above), so no release runs here."
    exit 3
fi
current=${head#refs/heads/}
if [ -z "$head" ]; then
    wrong_branch "$(setting branch 2>/dev/null)"
fi
# Untracked files count too, whatever the server's git config says: a script
# dropped into the checkout must not run unreviewed
if ! changes=$(git -C "$checkout" status --porcelain --untracked-files=normal 9>&-); then
    say "git status failed in ResourcePackScripts (its reason is above), so no release runs here."
    exit 3
fi
if [ -n "$changes" ]; then
    say "Someone edited ResourcePackScripts on the server. That change must go through a pull request; until then no release runs here."
    exit 3
fi
fetched=yes
fetch_error=$(GIT_TERMINAL_PROMPT=0 git -C "$checkout" fetch --quiet origin "+refs/heads/$current:refs/remotes/origin/$current" 2>&1 9>&-) || fetched=no
if ! git -C "$checkout" rev-parse --verify --quiet "refs/remotes/origin/$current" >/dev/null 9>&-; then
    # Most likely a branch made on the server: name the folder's own, if the
    # reader can tell before the update
    declared=$(setting branch 2>/dev/null)
    if [ -n "$declared" ] && [ "$declared" != "$current" ]; then
        wrong_branch "$declared"
    fi
    say "GitHub has no branch '$current' (or can't be reached, and it was never fetched here), so ResourcePackScripts can't follow it."
    exit 3
fi
if [ "$fetched" = no ]; then
    say "Couldn't fetch '$current' from GitHub ($(printf '%s\n' "$fetch_error" | head -n 1)), so this release uses the version fetched last."
fi
# merge --ff-only alone would take a checkout that is ahead of GitHub as
# "already up to date", and a commit made here would go out unreviewed
if ! git -C "$checkout" merge-base --is-ancestor HEAD "refs/remotes/origin/$current" 9>&-; then
    say "ResourcePackScripts has commits that GitHub's $current doesn't. Either they were made on the server and need a pull request, or GitHub's history was rewritten and the checkout needs resetting to it. Until then no release runs here."
    exit 3
fi
if ! git -C "$checkout" merge --ff-only --quiet "refs/remotes/origin/$current" >/dev/null 9>&-; then
    say "Couldn't bring ResourcePackScripts up to date with GitHub's $current (git's reason is above)."
    exit 3
fi

# 4. This folder's settings, read by the reader just brought up to date. It
#    exits 2 when automation.conf is wrong; any other failure is the reader
#    itself, as it is on GitHub
side=$(setting side) && branch=$(setting branch) \
    && replace_existing=$(setting replace_existing) && wrapper=$(setting wrapper)
case $? in
0) ;;
2)
    say "This folder's automation.conf is invalid (see above). Fix the line named there, or rewrite the file: python3 ResourcePackScripts/automation/install.py --side <test|production> --force"
    exit 2
    ;;
*)
    say "ResourcePackScripts's automation/automation_conf.py failed (see above), as it is on GitHub's $current, so no release can start. Once a fix is on GitHub, the next release picks it up."
    exit 2
    ;;
esac
if [ "$branch" != "$current" ]; then
    wrong_branch "$branch"
fi

# 5. Hand over with exec: the release takes this process's place, so what
#    Architect waits for and stops is the release itself, and no shell is left
#    behind (descriptor 9, and with it the lock, is inherited either way). The
#    wrapper and the scripts run with sh, as Architect runs scripts, so none of
#    them needs the executable bit
script="$checkout/automation/scripts/$name"
if [ ! -f "$script" ]; then
    say "ResourcePackScripts has no release script called $name."
    exit 2
fi
entry="$checkout/automation/pipeline/run.sh"
if [ "$wrapper" = yes ] && [ ! -f "$entry" ]; then
    say "automation.conf asks for the pipeline wrapper, but ResourcePackScripts has no automation/pipeline/run.sh."
    exit 2
fi
# What the release runs with: the scripts read replace_existing, and the
# wrapper records the side, the branch and the commit in the run's summary
RP_AUTOMATION_COMMIT=$(git -C "$checkout" rev-parse HEAD 9>&-) || exit 3
RP_AUTOMATION_SIDE=$side
RP_AUTOMATION_BRANCH=$branch
RP_AUTOMATION_REPLACE_EXISTING=$replace_existing
export RP_AUTOMATION_SIDE RP_AUTOMATION_BRANCH RP_AUTOMATION_REPLACE_EXISTING RP_AUTOMATION_COMMIT
say "Releasing with ResourcePackScripts $branch at $(git -C "$checkout" rev-parse --short HEAD 9>&-)."
trap - EXIT
if [ "$wrapper" = yes ]; then
    exec sh "$entry" "$script" "$@"
fi
exec sh "$script" "$@"
