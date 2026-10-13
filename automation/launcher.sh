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
# other code is the release's own. Each of its refusals also leaves a note for
# the dashboard's Resource packs page in runs/refused.jsonl.

folder=$(cd "$(dirname "$0")" && pwd) || exit 2
cd "$folder" || exit 2
name=$(basename "$0")
checkout="$folder/ResourcePackScripts"

say() {
    printf 'release launcher: %s\n' "$*" >&2
}

# The release's own arguments, for the note a refusal leaves
arg_pack=${1-} arg_owner=${2-} arg_repo=${3-} arg_tag=${4-} arg_title=
if [ $# -gt 4 ]; then
    arg_title=$(shift 4; printf '%s' "$*")
fi

# A refusal's note for the dashboard, one JSON line in runs/refused.jsonl, as
# the wrapper writes for a release the lock refused. Only once runs/ exists, so
# an uninstalled folder gets none; with python3 -I, so nothing in this folder
# or the checkout runs; without "(see above)" and the like, which mean nothing
# on the dashboard. A note that can't be written changes nothing about the
# refusal itself
note() {
    [ -d "$folder/runs" ] || return 0
    python3 -I -c '
import datetime, json, re, sys
path, script, code, reason, pack, owner, repo, tag, title = sys.argv[1:]
reason = re.sub(r" ?\([^()]*above\)", "", reason)
entry = {"at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"), "script": script,
         "pack": pack or None, "owner": owner or None, "repo": repo or None, "tag": tag or None,
         "name": title or None, "user": None, "by": "launcher", "code": int(code), "reason": reason}
with open(path, "a", encoding="utf-8") as fh:
    fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
' "$folder/runs/refused.jsonl" "$name" "$1" "$2" \
        "$arg_pack" "$arg_owner" "$arg_repo" "$arg_tag" "$arg_title" 9>&- 2>/dev/null || true
}

# Say why no release runs ($2, then any further lines), note it, and stop with
# the launcher's exit code ($1)
refuse() {
    code=$1 reason=$2
    shift 2
    say "$reason"
    for line in "$@"; do
        say "$line"
    done
    note "$code" "$reason"
    exit "$code"
}

setting() {
    python3 "$checkout/automation/automation_conf.py" get "$folder/automation.conf" "$1"
}

# The checkout must be on the branch the folder follows ($1, when known)
wrong_branch() {
    refuse 3 "ResourcePackScripts is on '${current:-no branch}', but automation.conf says '${1:-?}'. Switch it with: git -C ResourcePackScripts switch ${1:-<branch>}"
}

# 1. An installed folder. Its settings are read only once the checkout is up
#    to date (step 4), so that a fix to the reader on GitHub reaches this
#    folder by itself
if [ ! -f "$folder/automation.conf" ] || [ ! -e "$checkout/.git" ]; then
    refuse 2 "This automation folder isn't installed: it has no automation.conf, or no ResourcePackScripts checkout." \
        "Install it with: python3 ResourcePackScripts/automation/install.py --side <test|production>"
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
    refuse 75 "Another release is running${running:+: $running}. Start this one again once it has finished."
    ;;
*)
    refuse 2 "Couldn't take the release lock (flock's reason is above), so no release runs here."
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
    refuse 3 "git can't read ResourcePackScripts (its reason is above), so no release runs here."
fi
current=${head#refs/heads/}
if [ -z "$head" ]; then
    wrong_branch "$(setting branch 2>/dev/null)"
fi
# Untracked files count too, whatever the server's git config says: a script
# dropped into the checkout must not run unreviewed
if ! changes=$(git -C "$checkout" status --porcelain --untracked-files=normal 9>&-); then
    refuse 3 "git status failed in ResourcePackScripts (its reason is above), so no release runs here."
fi
if [ -n "$changes" ]; then
    # What changed, as git status shows it: the first 10 lines, so the admin
    # knows what to take to a pull request or undo
    edited="Someone edited ResourcePackScripts on the server. That change must go through a pull request; until then no release runs here."
    say "$edited What git status shows:"
    printf '%s\n' "$changes" | head -n 10 | sed 's/^/release launcher:   /' >&2
    count=$(printf '%s\n' "$changes" | grep -c '')
    if [ "$count" -gt 10 ]; then
        say "and $((count - 10)) more: git -C ResourcePackScripts status lists them all."
    fi
    note 3 "$edited git status shows $count changed or new file(s)."
    exit 3
fi
# GIT_TERMINAL_PROMPT=0: a fetch that wants a password fails at once. The low
# speed limit: one that stalls, under 1000 bytes/s for 60 s, gives up. Either
# would otherwise hold the release lock until Architect stops the release
fetched=yes
fetch_error=$(GIT_TERMINAL_PROMPT=0 GIT_HTTP_LOW_SPEED_LIMIT=1000 GIT_HTTP_LOW_SPEED_TIME=60 \
    git -C "$checkout" fetch --quiet origin "+refs/heads/$current:refs/remotes/origin/$current" 2>&1 9>&-) || fetched=no
if ! git -C "$checkout" rev-parse --verify --quiet "refs/remotes/origin/$current" >/dev/null 9>&-; then
    # Most likely a branch made on the server: name the folder's own, if the
    # reader can tell before the update
    declared=$(setting branch 2>/dev/null)
    if [ -n "$declared" ] && [ "$declared" != "$current" ]; then
        wrong_branch "$declared"
    fi
    refuse 3 "GitHub has no branch '$current' (or can't be reached, and it was never fetched here), so ResourcePackScripts can't follow it."
fi
if [ "$fetched" = no ]; then
    say "Couldn't fetch '$current' from GitHub ($(printf '%s\n' "$fetch_error" | head -n 1)), so this release uses the version fetched last."
fi
# merge --ff-only alone would take a checkout that is ahead of GitHub as
# "already up to date", and a commit made here would go out unreviewed
if ! git -C "$checkout" merge-base --is-ancestor HEAD "refs/remotes/origin/$current" 9>&-; then
    refuse 3 "ResourcePackScripts has commits that GitHub's $current doesn't. Either they were made on the server and need a pull request, or GitHub's history was rewritten and the checkout needs resetting to it. Until then no release runs here."
fi
if ! git -C "$checkout" merge --ff-only --quiet "refs/remotes/origin/$current" >/dev/null 9>&-; then
    refuse 3 "Couldn't bring ResourcePackScripts up to date with GitHub's $current (git's reason is above)."
fi

# 4. This folder's settings, read by the reader just brought up to date. It
#    exits 2 when automation.conf is wrong; any other failure is the reader
#    itself, as it is on GitHub
side=$(setting side) && branch=$(setting branch) \
    && replace_existing=$(setting replace_existing) && wrapper=$(setting wrapper)
case $? in
0) ;;
2)
    refuse 2 "This folder's automation.conf is invalid (see above). Fix the line named there, or rewrite the file: python3 ResourcePackScripts/automation/install.py --side <test|production> --force"
    ;;
*)
    refuse 2 "ResourcePackScripts's automation/automation_conf.py failed (see above), as it is on GitHub's $current, so no release can start. Once a fix is on GitHub, the next release picks it up."
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
    refuse 2 "ResourcePackScripts has no release script called $name."
fi
entry="$checkout/automation/pipeline/run.sh"
if [ "$wrapper" = yes ] && [ ! -f "$entry" ]; then
    refuse 2 "automation.conf asks for the pipeline wrapper, but ResourcePackScripts has no automation/pipeline/run.sh."
fi
# What the release runs with: the scripts read replace_existing, and the
# wrapper records the side, the branch and the commit in the run's summary
RP_AUTOMATION_COMMIT=$(git -C "$checkout" rev-parse HEAD 9>&-) \
    || refuse 3 "git couldn't read which commit ResourcePackScripts is on (its reason is above)."
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
