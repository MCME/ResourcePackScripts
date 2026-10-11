#!/usr/bin/env python3
"""rp-release.py — a log and a summary for every resource pack release, for
the dashboard's Resource packs page (ADR-040). Standard library only.

pipeline/run.sh uses it around each release script. ARGS are the release
script's own: <pack> <owner> <repo> <tag> <release name>.

    rp-release.py log --runs DIR --id ID --script NAME [--server-log FILE] -- ARGS
        The script's output, stdout and stderr together, on stdin. Every line
        goes to DIR/ID.log with a timestamp. All but the generator's --debug
        lines also go to DIR/ID.console.log and to stdout, which the plugin
        writes to the server console. DIR/current.json says what is running.

    rp-release.py summary --runs DIR --id ID --exit CODE|interrupted
        DIR/ID.json from DIR/ID.log: steps, zips, warnings, errors and the
        release. Then the log is gzipped, current.json removed and old logs
        pruned. Prints one line for the console.

    rp-release.py refused --runs DIR --script NAME [--server-log FILE] -- ARGS
        Another release holds the lock: says which, and notes the attempt in
        DIR/refused.jsonl.

Runs from before the pipeline are read back from a server log once:

    rp-release.py backfill --runs DIR --date YYYY-MM-DD [--automation DIR] SERVER_LOG
        (--automation: the folder the runs ran in, to show its paths shortened)

Summaries are DIR/<id>.json, where <id> is <YYYYmmdd-HHMMSS>-<pack>-<tag>.
They hold the run's folded console, never the --debug lines themselves.
"""

import argparse
import datetime
import glob
import gzip
import json
import os
import re
import shutil
import sys
import time

VERSION = 2
KEEP_FULL_LOGS = 30
KEEP_CONSOLE_LOGS = 200
MAX_EVENTS = 3000
SERVER_LOG_TAIL = 1024 * 1024
# A zip with fewer files than this share of the baseline's is a notice, not a
# problem. The converter getting better looks exactly like the converter
# breaking half-way, and only a person can tell those apart, so this reports
# and does not condemn.
SHRINK_LIMIT = 0.9

ID_RE = re.compile(r"^\d{8}-\d{6}-[A-Za-z0-9._-]+$")
STAMP = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?) (.*)$")
STEP = re.compile(r"^(compiling \S+ RP zips|releasing \S+ RP zips|\S+-(?:Sodium|Vanilla|Lite)(?:-Footprints)?)$")
# generateVanilla --debug: one line per model and texture, ~120,000 per run
DEBUG = [
    ("blockstates", re.compile(r"^Working on blockstate file: ")),
    ("items", re.compile(r"^Working on item(?: definition)? file: ")),
    ("vanillaModelsRead", re.compile(r"^\s+Reading vanilla model ")),
    ("modelsCopied", re.compile(r"^\s+Copying model ")),
    ("texturesCopied", re.compile(r"^\s+Copying texture: ")),
    ("modelsConverted", re.compile(r"^\s+Converting model: ")),
    ("sharedParents", re.compile(r"^\s+Shared parent: ")),
    ("builtinSkipped", re.compile(r"^\s+Skipping built-in model ")),
]
GEN_INFO = re.compile(r"^(Source path|Output path|Vanilla path): (.*)$")
RELEASE_URL = re.compile(r"^https://github\.com/[^/\s]+/[^/\s]+/releases/tag/\S+$")
TAG_EXISTS = re.compile(r"Release\.tag_name already exists|HTTP 422: Validation Failed")
ERROR = re.compile(r"\b(error|Error|ERROR|cannot|HTTP \d{3}|failed|Failed|denied|fatal:|No such file|Traceback)")
HARMLESS = [
    # the first run in a folder has no release/ to remove yet
    re.compile(r"^rm: cannot remove 'release': No such file or directory$"),
]
SERVER_LINE = re.compile(r"^\[(\d\d:\d\d:\d\d)\] \[([^\]/]+)/(\w+)\]: (.*)$")
RP_COMMAND = re.compile(r"^(\S+) issued server command: (/rp release\b.*)$")


# ── small helpers ─────────────────────────────────────────────────────

def now():
    return datetime.datetime.now().astimezone()


def iso(dt):
    return dt.isoformat(timespec="seconds")


def write_json(path, data, mode=0o644):
    tmp = f"{path}.tmp{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, separators=(",", ":"))
        fh.write("\n")
    os.chmod(tmp, mode)
    os.replace(tmp, path)


def read_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def release_args(args):
    """<pack> <owner> <repo> <tag> <name...> as the plugin passes them."""
    args = list(args)
    get = lambda i: args[i] if len(args) > i else None
    return {"pack": get(0), "owner": get(1), "repo": get(2), "tag": get(3),
            "name": " ".join(args[4:]) or None}


def debug_kind(text):
    for kind, rx in DEBUG:
        if rx.match(text):
            return kind
    return None


def last_segment(text):
    # objmc redraws its progress with \r; keep what the terminal would show
    parts = [p for p in text.split("\r") if p.strip()]
    return parts[-1] if parts else ""


def find_user(server_log, tag, at, window=300):
    """Who ran /rp release for this tag, from the server log's tail."""
    if not server_log or not tag:
        return None
    try:
        with open(server_log, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - SERVER_LOG_TAIL))
            tail = fh.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return None
    found = None
    for line in tail:
        m = SERVER_LINE.match(line)
        if not m or m.group(2) != "Server thread":
            continue
        c = RP_COMMAND.match(m.group(4))
        if not c:
            continue
        parts = c.group(2).split()
        if len(parts) < 4 or parts[3] != tag:
            continue
        h, mi, s = map(int, m.group(1).split(":"))
        logged = h * 3600 + mi * 60 + s
        current = at.hour * 3600 + at.minute * 60 + at.second
        if (current - logged) % 86400 <= window:
            found = c.group(1)
    return found


# ── the live logger ───────────────────────────────────────────────────

def cmd_log(opts):
    runs, run_id = opts.runs, opts.id
    started = now()
    meta = {"version": VERSION, "id": run_id, "script": opts.script, **release_args(opts.args),
            "user": find_user(opts.server_log, release_args(opts.args)["tag"], started),
            "started": iso(started), "pid": os.getppid()}
    progress = {**meta, "step": None, "stepStarted": None, "lines": 0, "consoleLines": 0,
                "debugLines": 0, "warnings": 0, "errors": 0, "updated": iso(started),
                "consoleLog": f"{run_id}.console.log"}

    full = console = None
    try:
        full = open(os.path.join(runs, f"{run_id}.log"), "w", encoding="utf-8")
        full.write("#meta " + json.dumps(meta, ensure_ascii=False) + "\n")
        console = open(os.path.join(runs, f"{run_id}.console.log"), "w", encoding="utf-8")
    except OSError as err:
        print(f"WARNING!!! rp-release: cannot write the run's log ({err}); the release goes on without it", flush=True)
        full = console = None

    current_path = os.path.join(runs, "current.json")
    last_write = 0.0

    def save_progress(force=False):
        nonlocal last_write
        t = time.monotonic()
        if not force and t - last_write < 1.0:
            return
        last_write = t
        progress["updated"] = iso(now())
        try:
            write_json(current_path, progress)
        except OSError:
            pass

    save_progress(force=True)
    out = sys.stdout
    for raw in sys.stdin.buffer:
        text = raw.decode("utf-8", "replace").rstrip("\n")
        try:
            text = last_segment(text) if "\r" in text else text
            stamp = now().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
            kind = debug_kind(text)
            progress["lines"] += 1
            if full:
                full.write(f"{stamp} {text}\n")
            if kind:
                progress["debugLines"] += 1
                save_progress()
                continue
            progress["consoleLines"] += 1
            if console:
                console.write(f"{stamp} {text}\n")
                console.flush()
            if STEP.match(text):
                progress["step"], progress["stepStarted"] = text, iso(now())
                save_progress(force=True)
            elif re.match(r"^\s*WARNING!", text):
                progress["warnings"] += 1
            elif ERROR.search(text) and not any(rx.match(text) for rx in HARMLESS):
                progress["errors"] += 1
            save_progress()
        except Exception:  # never let the log break a release
            pass
        try:
            out.write(text + "\n")
            out.flush()
        except (BrokenPipeError, OSError):
            pass
    for fh in (full, console):
        try:
            fh and fh.close()
        except OSError:
            pass
    save_progress(force=True)


# ── reading a run back ────────────────────────────────────────────────

def fold(lines):
    """Events from (datetime, text) lines: steps, zips, git, warnings, errors,
    tracebacks, with --debug lines counted per step instead of kept."""
    events, steps = [], []
    debug_at = {}
    step = None
    start = lines[0][0] if lines else None
    i = 0
    after_release = False

    def emit(kind, dt, text="", **extra):
        e = {"t": dt.strftime("%H:%M:%S"), "s": round((dt - start).total_seconds(), 1),
             "kind": kind, "text": text, "step": step}
        e.update(extra)
        events.append(e)
        return e

    while i < len(lines):
        dt, text = lines[i]
        if steps:
            steps[-1]["end"] = dt
        if text.strip() == "":
            i += 1
            continue
        if STEP.match(text) and not after_release:
            step = text
            steps.append({"name": text, "start": dt, "end": dt})
            after_release = text.startswith("releasing")
            emit("step", dt, text)
            i += 1
            continue
        kind = debug_kind(text)
        if kind:
            d = debug_at.get(step)
            if d is None:
                d = debug_at[step] = emit("debug", dt, "", counts={}, lines=0, until=None)
            d["counts"][kind] = d["counts"].get(kind, 0) + 1
            d["lines"] += 1
            d["until"] = dt.strftime("%H:%M:%S")
            i += 1
            continue
        if text.startswith("7-Zip "):
            info = {"files": None, "folders": None, "inBytes": None, "outBytes": None, "ok": False}
            name = ""
            j = i + 1
            while j < len(lines):
                s = lines[j][1]
                if (m := re.match(r"Creating archive: (.*)", s)) or (m := re.match(r"Open archive: (.*)", s)):
                    name = os.path.basename(m.group(1).strip())
                elif (m := re.match(r"Add new data to archive: (?:(\d+) folders?, )?(\d+) files?, (\d+) bytes", s)):
                    info.update(folders=int(m.group(1) or 0), files=int(m.group(2)), inBytes=int(m.group(3)))
                elif (m := re.match(r"Archive size: (\d+) bytes", s)):
                    info["outBytes"] = int(m.group(1))
                elif s.startswith("Everything is Ok"):
                    info["ok"] = True
                    break
                elif re.match(r"^(ERROR|System ERROR|Break signaled)", s):
                    break
                j += 1
            emit("zip", dt, name, **info)
            if steps and j < len(lines):
                steps[-1]["end"] = lines[j][0]
            i = j + 1
            continue
        if re.match(r"Updating [0-9a-f]+\.\.[0-9a-f]+$", text):
            detail, summary = [text], text
            j = i + 1
            while j < len(lines) and (lines[j][1].startswith(" ") or lines[j][1] == "Fast-forward"):
                s = lines[j][1]
                detail.append(s)
                if re.match(r"\s*\d+ files? changed", s):
                    summary = f"{text} · {s.strip()}"
                j += 1
            emit("git", dt, summary, detail=detail)
            i = j
            continue
        if text.startswith("From https://github.com/") or text.startswith("From github.com:"):
            detail = [text]
            j = i + 1
            while j < len(lines) and re.match(r"^\s+(\S+\.\.\S+|\* \[new (branch|tag)\]|\+ \S+|- \[deleted\])", lines[j][1]):
                detail.append(lines[j][1])
                j += 1
            repo = re.split(r"github\.com[/:]", text, maxsplit=1)[1]
            emit("git", dt, f"git fetch {repo}: {len(detail) - 1} ref update(s)", detail=detail)
            i = j
            continue
        if GEN_INFO.match(text):
            vals = {}
            j = i
            while j < len(lines) and (m := GEN_INFO.match(lines[j][1])):
                vals[m.group(1)] = m.group(2)
                j += 1
            emit("gen", dt, f"generateVanilla: {vals.get('Source path', '?')} → {vals.get('Output path', '?')}"
                 f" (vanilla resources: {vals.get('Vanilla path', '?')})")
            i = j
            continue
        if text in ("Generating vanilla resource pack!",) or text.startswith("Processing Sodium RP in:"):
            i += 1
            continue
        if text.startswith("Error running process script:"):
            command, detail = text, []
            j = i + 1
            while j < len(lines):
                s = lines[j][1]
                if s.startswith("Script error output (stderr):"):
                    detail.append(s)
                    j += 1
                    while j < len(lines) and lines[j][1].strip() != "":
                        detail.append(lines[j][1])
                        j += 1
                    break
                if s.strip() not in ("%",):
                    detail.append(s.replace("\\Reading", "Reading"))
                j += 1
            mo = re.search(r"'--out', '([^']+)'", command)
            model = mo.group(1).rsplit("/", 1)[-1].removesuffix(".json") if mo else "?"
            code = re.search(r"returned non-zero exit status (\d+)", command)
            exc = next((d for d in reversed(detail) if re.match(r"^\w+(Error|Exception):", d)), "")
            emit("objmc", dt, f"objmc failed on {model}" + (f" (exit {code.group(1)})" if code else ""),
                 command=command, detail=detail, exc=exc)
            i = j
            continue
        if text.startswith("Traceback (most recent call last):"):
            frames = []
            j = i + 1
            while j < len(lines) and lines[j][1].startswith(" "):
                frames.append(lines[j][1])
                j += 1
            exc = lines[j][1] if j < len(lines) else ""
            emit("trace", dt, exc, frames=frames)
            i = j + 1
            continue
        if text.startswith("usage: generateVanilla.py"):
            j = i + 1
            while j < len(lines) and lines[j][1].startswith(" "):
                j += 1
            i = j
            continue
        if re.match(r"^\s*WARNING!+", text):
            clean = re.sub(r"^\s*WARNING!+\s*", "", text)
            prev = events[-1] if events else None
            if prev and prev["kind"] == "warn" and prev["text"] == clean:
                prev["repeat"] = prev.get("repeat", 1) + 1
            else:
                emit("warn", dt, clean)
            i += 1
            continue
        if RELEASE_URL.match(text):
            emit("release", dt, text)
            i += 1
            continue
        if TAG_EXISTS.search(text):
            repo = re.search(r"repos/([^/\s]+)/([^/\s)]+)/releases", text)
            known = next((e for e in events if e["kind"] == "exists"), None)
            if not known:
                known = emit("exists", dt, "The release already existed, so it was not created again. The upload replaces its assets.")
            if repo:
                known.update(owner=repo.group(1), repo=repo.group(2))
            i += 1
            continue
        if ERROR.search(text) and not any(rx.match(text) for rx in HARMLESS):
            emit("err", dt, text)
        else:
            emit("out", dt, text)
        i += 1

    for e in events:
        if e["kind"] == "debug" and e.get("until") is None:
            e["until"] = e["t"]
    for s in steps:
        s["startS"] = round((s["start"] - start).total_seconds(), 1)
        s["endS"] = round((s["end"] - start).total_seconds(), 1)
    return events, steps


def previous_baseline(runs, pack, run_id):
    """Zip file counts to measure this run against: the pack's previous release
    that did not fail.

    A failed run is skipped on purpose. If a release broke half-way, its counts
    must not become the bar the next one is held to. A run whose only finding
    was that a zip got smaller does not fail, so a deliberate drop becomes the
    next baseline and stops being reported after one release instead of being
    repeated for every release thereafter.
    """
    for path in sorted(glob.glob(os.path.join(runs, "*.json")), reverse=True):
        name = os.path.basename(path)[:-5]
        if name >= run_id or not ID_RE.match(name):
            continue
        data = read_json(path)
        if not data or data.get("pack") != pack or data.get("status") not in ("ok", "warnings"):
            continue
        zips = {z["name"]: z["files"] for z in data.get("zips", []) if z.get("files")}
        if zips:
            return data.get("tag"), zips
    return None, {}


LATE_STEP = "Error output, logged when the run ended"


def summarize(runs, run_id, meta, lines, exit_code, source, ended=None, console_lines=None, late_after_release=False):
    events, steps = fold(lines)
    if late_after_release:
        # Before the pipeline the plugin logged stderr only when a run ended
        for e in events:
            if e["step"] and e["step"].startswith("releasing") and e["kind"] not in ("step", "release", "exists"):
                e["late"], e["step"] = True, LATE_STEP
    started = lines[0][0] if lines else now()
    ended = ended or (lines[-1][0] if lines else started)
    problems = []
    notices = []
    prev_tag, prev_zips = previous_baseline(runs, meta.get("pack"), run_id)
    zips = []
    for e in events:
        if e["kind"] != "zip":
            continue
        z = {"name": e["text"], "files": e["files"], "folders": e["folders"], "inBytes": e["inBytes"],
             "outBytes": e["outBytes"], "ok": e["ok"], "step": e["step"], "previousFiles": prev_zips.get(e["text"])}
        if not e["ok"]:
            problems.append(f"7-Zip did not finish {z['name']}.")
        elif not z["files"]:
            problems.append(f"{z['name']} is empty.")
            e["bad"] = "empty"
        elif z["previousFiles"] and z["files"] < z["previousFiles"] * SHRINK_LIMIT:
            notices.append(f"{z['name']} has {z['files']:,} files; the previous release ({prev_tag}) had {z['previousFiles']:,}.")
            e["bad"] = "shrunk"
        zips.append(z)
    errors = [e for e in events if e["kind"] in ("err", "trace", "objmc")]
    warnings = [e for e in events if e["kind"] == "warn"]
    has_release_step = any(s["name"].startswith("releasing") for s in steps)
    url = next((e["text"] for e in events if e["kind"] == "release"), None)
    existed = any(e["kind"] == "exists" for e in events)
    if has_release_step and not url and not existed:
        problems.append("No GitHub release was created.")
    if exit_code == "interrupted":
        problems.append("The run stopped before it finished.")
    for s in steps:
        mine = [e for e in events if e["step"] == s["name"]]
        if any(e["kind"] in ("err", "trace", "objmc") or e.get("bad") == "empty" or (e["kind"] == "zip" and not e["ok"]) for e in mine):
            s["status"] = "failed"
        elif any(e["kind"] == "warn" or e.get("bad") == "shrunk" for e in mine):
            s["status"] = "warnings"
        else:
            s["status"] = "ok"
    # Two different questions, which the old single status ran together: did the
    # release publish, and do the checks like what they see? A release that
    # published is never reported as a failure for something a check noticed.
    published = bool(url or existed)
    outcome = ("interrupted" if exit_code == "interrupted"
               else "published" if published else "unpublished")
    checks = ("problems" if (errors or problems)
              else "warnings" if (warnings or notices) else "ok")
    status = ("interrupted" if exit_code == "interrupted"
              else "failed" if (errors or problems)
              else "warnings" if (warnings or notices) else "ok")
    debug_total = sum(e["lines"] for e in events if e["kind"] == "debug")
    truncated = len(events) > MAX_EVENTS
    summary = {
        "version": VERSION, "id": run_id, "source": source, "script": meta.get("script"),
        "pack": meta.get("pack"), "owner": meta.get("owner"), "repo": meta.get("repo"), "tag": meta.get("tag"),
        "name": meta.get("name"), "user": meta.get("user"),
        "started": iso(started), "ended": iso(ended), "durationS": round((ended - started).total_seconds()),
        "exitCode": None if exit_code == "interrupted" else exit_code,
        "outcome": outcome, "checks": checks, "status": status,
        "problems": problems, "notices": notices,
        "release": {"url": url, "existed": existed, "owner": meta.get("owner"), "repo": meta.get("repo"), "tag": meta.get("tag")},
        "steps": [{"name": s["name"], "start": s["start"].strftime("%H:%M:%S"), "end": s["end"].strftime("%H:%M:%S"),
                   "startS": s["startS"], "endS": s["endS"], "status": s["status"]} for s in steps],
        "zips": zips,
        "counts": {"lines": len(lines), "consoleLines": console_lines if console_lines is not None else len(lines) - debug_total,
                   "debugLines": debug_total, "warnings": sum(e.get("repeat", 1) for e in warnings), "errors": len(errors)},
        "events": events[:MAX_EVENTS], "eventsTruncated": truncated,
        "log": None,
    }
    return summary


def shorten(events, folder):
    """Paths inside the automation folder, relative to it, as the page shows them."""
    prefixes = sorted({os.path.abspath(folder) + "/", os.path.realpath(folder) + "/"}, key=len, reverse=True)

    def short(value):
        if isinstance(value, str):
            for prefix in prefixes:
                value = value.replace(prefix, "")
        return value

    for e in events:
        for key in ("text", "command", "exc"):
            if key in e:
                e[key] = short(e[key])
        for key in ("detail", "frames"):
            if key in e:
                e[key] = [short(v) for v in e[key]]


def read_run_log(path):
    meta, lines = {}, []
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            raw = raw.rstrip("\n")
            if raw.startswith("#meta "):
                try:
                    meta = json.loads(raw[6:])
                except ValueError:
                    pass
                continue
            m = STAMP.match(raw)
            if not m:
                continue
            dt = datetime.datetime.fromisoformat(m.group(1)).astimezone()
            lines.append((dt, m.group(2)))
    return meta, lines


def prune(runs):
    ids = sorted(os.path.basename(p)[:-5] for p in glob.glob(os.path.join(runs, "*.json")) if ID_RE.match(os.path.basename(p)[:-5]))
    for old in ids[:-KEEP_FULL_LOGS]:
        for ext in (".log.gz", ".log"):
            try:
                os.remove(os.path.join(runs, old + ext))
            except FileNotFoundError:
                pass
    for old in ids[:-KEEP_CONSOLE_LOGS]:
        try:
            os.remove(os.path.join(runs, old + ".console.log"))
        except FileNotFoundError:
            pass


def cmd_summary(opts):
    runs, run_id = opts.runs, opts.id
    if not ID_RE.match(run_id):
        sys.exit(f"bad run id: {run_id}")
    log_path = os.path.join(runs, f"{run_id}.log")
    current_path = os.path.join(runs, "current.json")
    progress = read_json(current_path) or {}
    meta, lines = ({}, [])
    if os.path.exists(log_path):
        meta, lines = read_run_log(log_path)
    meta = {**progress, **meta} if progress.get("id") == run_id else meta
    exit_code = opts.exit if opts.exit == "interrupted" else int(opts.exit)
    ended = None
    if exit_code == "interrupted" and progress.get("id") == run_id and progress.get("updated"):
        ended = datetime.datetime.fromisoformat(progress["updated"])
    summary = summarize(runs, run_id, meta, lines, exit_code, "pipeline", ended=ended)
    shorten(summary["events"], os.path.join(runs, ".."))
    if os.path.exists(log_path):
        with open(log_path, "rb") as src, gzip.open(log_path + ".gz", "wb") as dst:
            shutil.copyfileobj(src, dst)
        os.remove(log_path)
        summary["log"] = f"{run_id}.log.gz"
    summary["consoleLog"] = f"{run_id}.console.log" if os.path.exists(os.path.join(runs, f"{run_id}.console.log")) else None
    write_json(os.path.join(runs, f"{run_id}.json"), summary)
    if progress.get("id") == run_id:
        try:
            os.remove(current_path)
        except FileNotFoundError:
            pass
    prune(runs)
    label = {"ok": "OK", "warnings": "OK with warnings", "failed": "FAILED", "interrupted": "INTERRUPTED"}[summary["status"]]
    said = {"published": "released", "unpublished": "nothing released", "interrupted": "cut off"}[summary["outcome"]]
    zips = ", ".join(f"{z['name']} {z['files'] or 0:,} files" for z in summary["zips"])
    print(f"Release run {run_id}: {label}, {said}. {summary['counts']['warnings']} warning(s), {summary['counts']['errors']} error(s). {zips}", flush=True)
    for p in summary["problems"]:
        print(f"WARNING!!! {p}", flush=True)
    for n in summary["notices"]:
        print(f"NOTICE!!! {n}", flush=True)


def recheck_summary(data):
    """Bring an existing summary's verdict up to the current rules.

    Works from what the summary already records, so no log is needed and runs
    whose logs have been pruned can still be corrected. A zip that is smaller
    than its baseline moves from a problem to a notice, and the verdict is
    recomputed from that.
    """
    zips = data.get("zips") or []
    problems = list(data.get("problems") or [])
    notices = list(data.get("notices") or [])
    shrunk_steps = set()
    for z in zips:
        prev, files = z.get("previousFiles"), z.get("files")
        if prev and files and files < prev * SHRINK_LIMIT:
            problems = [p for p in problems if not p.startswith(f"{z['name']} has ")]
            line = f"{z['name']} has {files:,} files; the previous release had {prev:,}."
            if not any(n.startswith(f"{z['name']} has ") for n in notices):
                notices.append(line)
            if z.get("step"):
                shrunk_steps.add(z["step"])
    counts = data.get("counts") or {}
    errors, warnings = counts.get("errors") or 0, counts.get("warnings") or 0
    interrupted = data.get("status") == "interrupted"
    release = data.get("release") or {}
    published = bool(release.get("url") or release.get("existed"))
    data["problems"], data["notices"] = problems, notices
    data["outcome"] = ("interrupted" if interrupted
                       else "published" if published else "unpublished")
    data["checks"] = ("problems" if (errors or problems)
                      else "warnings" if (warnings or notices) else "ok")
    data["status"] = ("interrupted" if interrupted
                      else "failed" if (errors or problems)
                      else "warnings" if (warnings or notices) else "ok")
    # A step whose only finding was a smaller zip is not a failed step either.
    if not errors:
        for step in data.get("steps") or []:
            if step.get("name") in shrunk_steps and step.get("status") == "failed":
                step["status"] = "warnings"
    data["version"] = VERSION
    return data


def cmd_recheck(opts):
    """Re-verdict stored runs, so history reads by the same rules as new runs."""
    reverdicted, filled = 0, 0
    for path in sorted(glob.glob(os.path.join(opts.runs, "*.json"))):
        name = os.path.basename(path)[:-5]
        if not ID_RE.match(name):
            continue
        data = read_json(path)
        if not data:
            continue
        was = (data.get("status"), data.get("outcome"), data.get("checks"))
        recheck_summary(data)
        now_ = (data.get("status"), data.get("outcome"), data.get("checks"))
        if was == now_:
            continue
        write_json(path, data)
        if was[0] != now_[0]:
            reverdicted += 1
            print(f"{name}: {was[0]} -> {now_[0]} ({now_[1]}, checks {now_[2]})", flush=True)
        else:
            filled += 1
    print(f"{reverdicted} run(s) changed verdict; {filled} kept theirs and gained the new fields.", flush=True)


def cmd_accept(opts):
    """Record that a run's notices were looked at and are what was intended."""
    path = os.path.join(opts.runs, f"{opts.id}.json")
    data = read_json(path)
    if not data:
        sys.exit(f"no such run: {opts.id}")
    data["baselineAccepted"] = {"reason": opts.reason, "by": opts.by, "at": iso(now())}
    write_json(path, data)
    print(f"{opts.id}: accepted by {opts.by} - {opts.reason}", flush=True)


def cmd_refused(opts):
    runs = opts.runs
    attempt = release_args(opts.args)
    at = now()
    current = read_json(os.path.join(runs, "current.json")) or {}
    user = find_user(opts.server_log, attempt["tag"], at)
    since = current.get("started", "")[11:19]
    who = f" by {current['user']}" if current.get("user") else ""
    step = f", now at {current['step']}" if current.get("step") else ""
    print(f"Another resource pack release is running: {current.get('pack') or '?'} {current.get('tag') or '?'}{who} since {since or '?'}{step}.", flush=True)
    print(f"Nothing was started for {attempt['pack']} {attempt['tag']}. Run /rp release again when it has finished.", flush=True)
    try:
        with open(os.path.join(runs, "refused.jsonl"), "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"at": iso(at), "script": opts.script, **attempt, "user": user,
                                 "running": {k: current.get(k) for k in ("id", "pack", "tag", "user", "started", "step")}},
                                ensure_ascii=False) + "\n")
    except OSError:
        pass


def cmd_backfill(opts):
    """Summaries for runs logged to the server log before the pipeline."""
    day = datetime.date.fromisoformat(opts.date)
    tz = now().tzinfo
    os.makedirs(opts.runs, exist_ok=True)
    raw = []
    with open(opts.server_log, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = SERVER_LINE.match(line.rstrip("\n"))
            if m:
                raw.append(m.groups())
    made = 0
    for i, (t, thread, _level, msg) in enumerate(raw):
        c = RP_COMMAND.match(msg)
        if thread != "Server thread" or not c:
            continue
        pool = next((th for _t, th, _l, m2 in raw[i + 1:i + 40] if th.startswith("pool-") and m2.startswith("[global] compiling")), None)
        if not pool:
            continue
        parts = c.group(2).split()
        lines = []
        for t2, th, _l, m2 in raw[i + 1:]:
            if th != pool:
                continue
            text = m2[9:] if m2.startswith("[global] ") else m2[8:] if m2.startswith("[global]") else m2
            dt = datetime.datetime.combine(day, datetime.time.fromisoformat(t2)).replace(tzinfo=tz)
            lines.append((dt, text))
        if not lines:
            continue
        started = datetime.datetime.combine(day, datetime.time.fromisoformat(t)).replace(tzinfo=tz)
        first = lines[0][1]
        pack = first.split()[1] if first.startswith("compiling ") else parts[2]
        run_id = f"{started:%Y%m%d-%H%M%S}-{safe(pack)}-{safe(parts[3] if len(parts) > 3 else 'untagged')}"
        path = os.path.join(opts.runs, f"{run_id}.json")
        if os.path.exists(path):
            continue
        meta = {"script": None, "pack": pack, "owner": None, "repo": None,
                "tag": parts[3] if len(parts) > 3 else None, "name": " ".join(parts[4:]) or None, "user": c.group(1)}
        # a pool thread is reused: stop at the next run's first line
        lines = cut_at_next_run(lines)
        summary = summarize(opts.runs, run_id, meta, lines, 0, "server-log", late_after_release=True)
        if opts.automation:
            shorten(summary["events"], opts.automation)
        summary["exitCode"] = None
        # the plugin passed owner and repo, but only gh's output shows them here
        url = summary["release"]["url"] or ""
        m = re.search(r"https://github\.com/([^/]+)/([^/]+)/releases/tag/", url)
        existed = next((e for e in summary["events"] if e["kind"] == "exists" and e.get("owner")), None)
        owner, repo = (m.group(1), m.group(2)) if m else (existed["owner"], existed["repo"]) if existed else (None, None)
        summary["owner"], summary["repo"] = owner, repo
        summary["release"].update(owner=owner, repo=repo)
        write_json(path, summary)
        made += 1
        print(f"{run_id}: {summary['status']}, {len(summary['events'])} events")
    print(f"{made} summaries written")


def cut_at_next_run(lines):
    for k in range(1, len(lines)):
        if lines[k][1].startswith("compiling ") and lines[k][1].endswith(" RP zips"):
            return lines[:k]
    return lines


def safe(text):
    return re.sub(r"[^A-Za-z0-9._-]", "_", text or "")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("log")
    p.add_argument("--runs", required=True)
    p.add_argument("--id", required=True)
    p.add_argument("--script", required=True)
    p.add_argument("--server-log")
    p.add_argument("args", nargs="*")
    p = sub.add_parser("summary")
    p.add_argument("--runs", required=True)
    p.add_argument("--id", required=True)
    p.add_argument("--exit", required=True)
    p = sub.add_parser("refused")
    p.add_argument("--runs", required=True)
    p.add_argument("--script", required=True)
    p.add_argument("--server-log")
    p.add_argument("args", nargs="*")
    p = sub.add_parser("recheck")
    p.add_argument("--runs", required=True)
    p = sub.add_parser("accept")
    p.add_argument("--runs", required=True)
    p.add_argument("--id", required=True)
    p.add_argument("--reason", required=True)
    p.add_argument("--by", required=True)
    p = sub.add_parser("backfill")
    p.add_argument("--runs", required=True)
    p.add_argument("--date", required=True)
    p.add_argument("--automation")
    p.add_argument("server_log")
    opts = parser.parse_args()
    {"log": cmd_log, "summary": cmd_summary, "refused": cmd_refused, "backfill": cmd_backfill,
     "recheck": cmd_recheck, "accept": cmd_accept}[opts.command](opts)


if __name__ == "__main__":
    main()
