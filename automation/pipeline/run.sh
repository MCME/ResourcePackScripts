#!/bin/sh
# run.sh — one resource pack release at a time, with a log and a summary per
# run for the dashboard's Resource packs page.
#
# The release launcher (automation/launcher.sh) hands over to it when the
# automation folder's automation.conf says wrapper=yes:
#
#     sh ResourcePackScripts/automation/pipeline/run.sh <release script> <pack> <owner> <repo> <tag> <name>
#
# It runs in the automation folder, under the launcher's release lock, and
# refuses to start without it. The script's output, stdout and stderr in
# order, still reaches the plugin (and so its log) as it happens, except the
# generator's --debug lines. Plain POSIX sh: the plugin starts the
# scripts with sh.

tool="$(cd "$(dirname "$0")" && pwd)/rp-release.py" || exit 2
# Who ran /rp release is in the log of the server that started the release:
# "auto" finds it (rp-release.py starting_server_log), also from the production
# folder, which every main server shares
server_log=${RP_SERVER_LOG:-auto}
runs=runs
script=$1
shift

# One release at a time: every release script builds in release/. The launcher
# took the lock and handed it down on descriptor 9. Locking runs/.lock afresh
# would reopen it and let the launcher's lock go for a moment, so check that
# descriptor 9 is runs/.lock and that this process holds its lock
if ! { [ /proc/self/fd/9 -ef "$runs/.lock" ] && flock -n 9; }; then
    echo "WARNING!!! pipeline/run.sh only runs under the release launcher, which holds the release lock. Nothing was started."
    exit 2
fi

# A run that was stopped left its progress behind: finish its summary first
if [ -f "$runs/current.json" ]; then
    stale=$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1])).get("id", ""))' "$runs/current.json" 2>/dev/null)
    if [ -n "$stale" ]; then
        python3 "$tool" summary --runs "$runs" --id "$stale" --exit interrupted >/dev/null 2>&1 9>&-
    fi
    rm -f "$runs/current.json"
fi

safe() { printf '%s' "$1" | tr -c 'A-Za-z0-9._-' '_'; }
id="$(date +%Y%m%d-%H%M%S)-$(safe "${1:-unknown}")-$(safe "${4:-untagged}")"
export RP_RELEASE_RUN="$id" PYTHONUNBUFFERED=1
exit_file="$runs/.$id.exit"

# The script runs without descriptor 9: this shell, and the subshell waiting
# for the script, hold the lock until the release has ended, and nothing the
# script starts can keep it afterwards
{ sh "$script" "$@" 9>&-; echo $? >"$exit_file"; } 2>&1 \
    | python3 "$tool" log --runs "$runs" --id "$id" --script "$(basename "$script")" --server-log "$server_log" -- "$@" 9>&-

code=$(cat "$exit_file" 2>/dev/null || echo 1)
rm -f "$exit_file"
python3 "$tool" summary --runs "$runs" --id "$id" --exit "$code" 9>&- \
    || echo "WARNING!!! The run's summary could not be written; runs/$id.log is kept"
exit "$code"
