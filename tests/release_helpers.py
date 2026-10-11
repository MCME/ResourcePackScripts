"""Helpers for the release automation's tests. Not a test module itself.

The stand-ins replace the tools the release scripts call. Each one logs its
call as a JSON line to the file named by $FAKE_LOG.
"""

import importlib.util
import json
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def load_rp_release():
    """automation/pipeline/rp-release.py as a module: its name has a dash, so it can't be imported."""
    spec = importlib.util.spec_from_file_location("rp_release", REPO_ROOT / "automation" / "pipeline" / "rp-release.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def wait_until_free(lock, seconds=10):
    """Wait until no process holds the release lock, the flock on the file at `lock`.

    A stopped release lets its lock go only when the last process holding it
    has ended, a moment after the one the test waited for. Every 10 ms this
    tries to take the lock on a fresh handle, and lets it go at once.
    """
    import fcntl  # POSIX only: the modules that import this file also run on Windows

    deadline = time.monotonic() + seconds
    while True:
        with open(lock, "a") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                pass
            else:
                return
        if time.monotonic() >= deadline:
            raise AssertionError(f"{lock} is still held {seconds} s after the release was stopped")
        time.sleep(0.01)


# 7-Zip's `7z a -y <zip> [<pattern>...] [-x!<pattern>...]`, run in the folder
# to zip: everything ("*") unless patterns are given, matched as 7-Zip does
# (dot files too), excluded names left out at any depth, and the report lines
# the wrapper reads. $FAKE_7Z_FAIL names a zip to fail on (exit 2);
# $FAKE_7Z_WARN one to make with a warning (exit 1).
FAKE_7Z = '''\
#!/usr/bin/env python3
import fnmatch, json, os, sys, zipfile

fd9 = os.path.exists("/proc/self/fd/9")
args = sys.argv[1:]
with open(os.environ["FAKE_LOG"], "a") as log:
    print(json.dumps({"tool": "7z", "args": args, "cwd": os.path.basename(os.getcwd()), "fd9": fd9}), file=log)
excludes = [arg[3:] for arg in args if arg.startswith("-x!")]
operands = [arg for arg in args[1:] if not arg.startswith("-")]
archive, patterns = operands[0], operands[1:] or ["*"]
print("7-Zip (a) 0.0 : a stand-in for the tests")
if archive == os.environ.get("FAKE_7Z_FAIL"):
    print("ERROR: the tests told 7-Zip to fail")
    sys.exit(2)


def excluded(path):
    return any(fnmatch.fnmatch(part, x) for part in path.split(os.sep) for x in excludes)


files = []
for top in sorted(os.listdir(".")):
    if top == archive or excluded(top) or not any(fnmatch.fnmatch(top, p) for p in patterns):
        continue
    if os.path.isdir(top):
        for root, dirs, names in os.walk(top):
            dirs[:] = sorted(d for d in dirs if not excluded(os.path.join(root, d)))
            files += [os.path.join(root, n) for n in sorted(names) if not excluded(os.path.join(root, n))]
    else:
        files.append(top)
print("Creating archive: " + archive)
with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
    for path in files:
        zf.write(path)
print(f"Add new data to archive: {len(files)} files, {sum(os.path.getsize(p) for p in files)} bytes")
print(f"Archive size: {os.path.getsize(archive)} bytes")
print("Everything is Ok")
sys.exit(1 if archive == os.environ.get("FAKE_7Z_WARN") else 0)
'''

# The GitHub CLI's `gh release view|create|upload <tag> ... --repo <owner/repo> ...`.
# Existing releases are "<owner/repo>@<tag>" lines in $FAKE_GH_RELEASES; create
# adds one. $FAKE_GH_FAIL names a command to fail as GitHub being down would.
FAKE_GH = '''\
#!/usr/bin/env python3
import json, os, sys

args = sys.argv[1:]
with open(os.environ["FAKE_LOG"], "a") as log:
    print(json.dumps({"tool": "gh", "args": args}), file=log)
store = os.environ["FAKE_GH_RELEASES"]
releases = open(store).read().split() if os.path.exists(store) else []
command, tag = args[1], args[2]
repo = args[args.index("--repo") + 1]
release = repo + "@" + tag
if command == os.environ.get("FAKE_GH_FAIL"):
    print("HTTP 502: Bad Gateway (https://api.github.com/graphql)", file=sys.stderr)
    sys.exit(1)
if command == "view":
    if release not in releases:
        print("release not found", file=sys.stderr)
        sys.exit(1)
    print("title:  an earlier release")
elif command == "create":
    if release in releases:
        print(f"HTTP 422: Validation Failed (https://api.github.com/repos/{repo}/releases)", file=sys.stderr)
        print("Release.tag_name already exists", file=sys.stderr)
        sys.exit(1)
    with open(store, "a") as f:
        print(release, file=f)
    print(f"https://github.com/{repo}/releases/tag/{tag}")
elif command == "upload":
    if release not in releases:
        print("release not found", file=sys.stderr)
        sys.exit(1)
    for path in args[3:args.index("--repo")]:
        if not os.path.isfile(path):
            print(f"{path}: not there to upload", file=sys.stderr)
            sys.exit(1)
'''

# git, for a pack's `git pull`: logs where it ran, whether it inherited
# descriptor 9 and GIT_TERMINAL_PROMPT. $FAKE_GIT_FAIL makes the pull fail.
FAKE_GIT = '''\
#!/usr/bin/env python3
import json, os, sys

fd9 = os.path.exists("/proc/self/fd/9")
with open(os.environ["FAKE_LOG"], "a") as log:
    print(json.dumps({"tool": "git", "args": sys.argv[1:], "cwd": os.path.basename(os.getcwd()), "fd9": fd9,
                      "prompt": os.environ.get("GIT_TERMINAL_PROMPT")}), file=log)
if os.environ.get("FAKE_GIT_FAIL"):
    print("fatal: unable to access 'https://github.com/MCME/RP-Test.git/': Could not resolve host: github.com",
          file=sys.stderr)
    sys.exit(1)
print("Already up to date.")
'''

# generateVanilla.py <source> <output> <vanilla> --objmc <path> [--debug] [--limit N]:
# writes a small converted pack (3 models; --limit N keeps N of them) with
# pack formats $FAKE_GENERATE_FORMATS ("88 97"). $FAKE_GENERATE_SAME makes
# --limit change nothing; $FAKE_GENERATE_FAIL stops it with a traceback.
FAKE_GENERATE = '''\
import json, os, sys

args = sys.argv[1:]
with open(os.environ["FAKE_LOG"], "a") as log:
    print(json.dumps({"tool": "generateVanilla", "args": args}), file=log)
source, output, vanilla = args[:3]
print("Generating vanilla resource pack!")
print("Source path: " + source)
print("Output path: " + output)
print("Vanilla path: " + vanilla)
if os.environ.get("FAKE_GENERATE_FAIL"):
    print("Traceback (most recent call last):")
    print('  File "generateVanilla.py", line 1, in <module>')
    print("ValueError: the tests told generateVanilla to fail")
    sys.exit(1)
lowest, highest = os.environ.get("FAKE_GENERATE_FORMATS", "88 97").split()
assets = os.path.join(output, "assets", "minecraft")
os.makedirs(os.path.join(assets, "textures", "block"), exist_ok=True)
os.makedirs(os.path.join(assets, "models", "block"), exist_ok=True)
with open(os.path.join(output, "pack.mcmeta"), "w") as f:
    json.dump({"pack": {"min_format": int(lowest), "max_format": int(highest), "description": "converted"}}, f)
with open(os.path.join(assets, "textures", "block", "stone.png"), "wb") as f:
    f.write(b"converted stone")
models = ["a", "b", "c"]
if "--limit" in args and not os.environ.get("FAKE_GENERATE_SAME"):
    models = models[: int(args[args.index("--limit") + 1])]
for model in models:
    with open(os.path.join(assets, "models", "block", model + ".json"), "w") as f:
        f.write("{}")
'''

FAKES = {"7z": FAKE_7Z, "gh": FAKE_GH, "git": FAKE_GIT}


def install_fakes(bin_dir, tools=("7z", "gh", "git")):
    """Put the named stand-ins into bin_dir, to go first on PATH."""
    bin_dir = Path(bin_dir)
    bin_dir.mkdir(parents=True, exist_ok=True)
    for tool in tools:
        path = bin_dir / tool
        path.write_text(FAKES[tool])
        path.chmod(0o755)


def calls(log, tool=None):
    """The stand-ins' logged calls, of one tool or of all, in order."""
    log = Path(log)
    if not log.exists():
        return []
    entries = [json.loads(line) for line in log.read_text().splitlines()]
    return [entry for entry in entries if tool is None or entry["tool"] == tool]
