#!/bin/sh
# run.sh — one resource pack release at a time, with a log and a summary per
# run for the dashboard's Resource packs page (ADR-040).
#
# The release scripts that MCME-Architect's /rp release starts hand themselves
# over in their first lines (scripts/install-rp-pipeline.sh adds them):
#
#     if [ -z "$RP_RELEASE_RUN" ] && [ -f "$(dirname "$0")/pipeline/run.sh" ]; then
#         exec sh "$(dirname "$0")/pipeline/run.sh" "$(basename "$0")" "$@"; fi
#
# Usage: sh pipeline/run.sh <release script> <pack> <owner> <repo> <tag> <name>
# The script runs from the automation folder, as the plugin runs it. Its
# output, stdout and stderr in order, still reaches the plugin (and so the
# server console) as it happens, except the generator's --debug lines.
# Plain POSIX sh: the plugin starts the scripts with sh.

here=$(cd "$(dirname "$0")" && pwd) || exit 1
cd "$here/.." || exit 1
tool="$here/rp-release.py"
server_log=${RP_SERVER_LOG:-../logs/latest.log}
runs=runs
script=$1
shift
mkdir -p "$runs" || exit 1

# One release at a time: every release script builds in release/
exec 9>>"$runs/.lock"
if ! flock -n 9; then
    python3 "$tool" refused --runs "$runs" --script "$script" --server-log "$server_log" -- "$@" 9>&-
    exit 75
fi

# A run that was killed left its progress behind: finish its summary first
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

{ sh "$script" "$@" 9>&-; echo $? >"$exit_file"; } 2>&1 \
    | python3 "$tool" log --runs "$runs" --id "$id" --script "$script" --server-log "$server_log" -- "$@" 9>&-

code=$(cat "$exit_file" 2>/dev/null || echo 1)
rm -f "$exit_file"
python3 "$tool" summary --runs "$runs" --id "$id" --exit "$code" 9>&- \
    || echo "WARNING!!! The run's summary could not be written; runs/$id.log is kept"
exit "$code"
