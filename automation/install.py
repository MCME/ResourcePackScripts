"""Install the release launchers into an automation folder, check one, or restore its backup.

Run it on the server, from the automation folder (resourcePackAutomation/), as
the user the Minecraft servers run as:

    python3 ResourcePackScripts/automation/install.py --side test
    python3 ResourcePackScripts/automation/install.py --side production
    python3 ResourcePackScripts/automation/install.py --check
    python3 ResourcePackScripts/automation/install.py --restore pre-automation-backup-<stamp>

Installing writes the launcher under every release script's name and the
folder's automation.conf, after backing up whatever it replaces or removes into
pre-automation-backup-<stamp>/. It takes the release lock first, and it puts
each new file in place with a rename, so even a release the lock can't see (an
old script takes none) goes on reading the script it started with. It never
touches the pack checkouts, Footprints/, the vanilla assets, release/ or the
run data in runs/.
"""

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

import automation_conf

HERE = Path(__file__).resolve().parent
LAUNCHER = HERE / "launcher.sh"
SCRIPT_NAMES = ("releaseVanillaSodium.sh", "releaseGeneral.sh", "releaseDynmap.sh")
TOOLS = ("git", "gh", "7z", "python3", "flock")
# HTTPS, SSH and scp-style remotes; GitHub ignores the case of owner and repository names
ORIGIN = re.compile(r"(?:^|[/@])github\.com[:/]MCME/ResourcePackScripts(?:\.git)?/?$", re.IGNORECASE)
LOCK_HELD = 75


class Refused(Exception):
    """The folder can't be installed, checked or restored as it is."""


class LockHeld(Exception):
    """A release is running in the folder."""


def lock_release(folder):
    """Take the launcher's release lock (runs/.lock), or raise LockHeld."""
    try:
        import fcntl
    except ImportError:
        raise Refused("install.py runs on the Linux server: this system has no flock") from None
    (folder / "runs").mkdir(exist_ok=True)
    handle = open(folder / "runs" / ".lock", "a")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        raise LockHeld() from None
    return handle


def git(checkout, *args):
    """A git command's output in checkout, or None if it failed."""
    result = subprocess.run(["git", "-C", str(checkout), *args], capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else None


def check_folder(folder):
    """The pack checkouts' names; Refused unless folder is a release system's automation folder."""
    checkout = folder / "ResourcePackScripts"
    if not (checkout / ".git").exists():
        raise Refused(f"{folder} has no ResourcePackScripts checkout, so it isn't an automation folder")
    result = subprocess.run(["git", "-C", str(checkout), "remote", "get-url", "origin"], capture_output=True, text=True)
    if result.returncode != 0:
        # "dubious ownership", for one: install.py runs as another user than the checkout's owner
        error = (result.stderr.strip().splitlines() or ["no reason given"])[0]
        raise Refused(f"git can't read ResourcePackScripts's origin: {error}")
    origin = result.stdout.strip()
    if not ORIGIN.search(origin):
        raise Refused(f"ResourcePackScripts's origin is {origin or 'empty'}, not MCME/ResourcePackScripts")
    packs = sorted(p.name for p in folder.iterdir() if p.is_dir() and p.name.endswith(("-Sodium", "-Vanilla")))
    if not packs:
        raise Refused(
            f"{folder} has no pack checkout (<Pack>-Sodium or <Pack>-Vanilla), so it isn't an automation folder"
        )
    return packs


def _check_shapes(folder):
    """Refused unless what install replaces or removes is a plain file, or for pipeline/ a plain folder."""
    for name in SCRIPT_NAMES + ("automation.conf", "pipeline"):
        path = folder / name
        plain = path.is_dir() if name == "pipeline" else path.is_file()
        if path.is_symlink() or (os.path.lexists(path) and not plain):
            kind = "a symlink" if path.is_symlink() else "not a plain " + ("folder" if name == "pipeline" else "file")
            raise Refused(f"{name} is {kind}, so install.py can't back it up as it is: replace it with a plain copy")


def _put(path, data, mode):
    """Write data to path as a new file. A symlink there is replaced, not followed;
    a shell still reading the old script goes on reading it; and a crash leaves the
    old file or the new one, never part of one."""
    tmp = path.with_name(f".{path.name}.install-tmp")
    try:
        tmp.write_bytes(data)
        tmp.chmod(mode)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _new_backup_folder(folder):
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = folder / f"pre-automation-backup-{stamp}"
    number = 2
    while backup.exists():
        backup = folder / f"pre-automation-backup-{stamp}-{number}"
        number += 1
    return backup


def _note_kept_conf(kept, settings):
    """Say so when an existing automation.conf was kept that differs from what was asked for."""
    if kept and kept != settings:
        listed = ", ".join(f"{key}={value}" for key, value in kept.items())
        print(f"automation.conf was kept as it is ({listed}), not as asked. To replace it, run again with --force.")


def _note_branch_mismatch(folder, branch):
    """Warn when the checkout isn't on the branch the folder follows: every release would refuse."""
    head = git(folder / "ResourcePackScripts", "symbolic-ref", "--quiet", "HEAD") or ""
    current = head[len("refs/heads/"):] if head.startswith("refs/heads/") else "no branch"
    if current != branch:
        print(
            f"Note: ResourcePackScripts is on {current}, but this folder follows {branch}, so every release here"
            " will refuse until they match. If this is the wrong folder for this side, undo the install with"
            f" --restore and its backup. Otherwise switch the checkout: git -C ResourcePackScripts switch {branch}"
        )


def install(folder, side, branch=None, force=False, locker=lock_release):
    """Install the launchers and automation.conf into folder; 0 when done."""
    folder = Path(folder).resolve()
    check_folder(folder)
    _check_shapes(folder)
    settings = dict(automation_conf.DEFAULTS[side])
    if branch:
        settings["branch"] = branch
    try:
        conf_text = automation_conf.render(settings)
    except automation_conf.ConfError as e:
        # Only --branch can be wrong here, and the line number would point into render()'s own text
        raise Refused(f"--branch {settings['branch']!r}: {re.sub(r'^line [0-9]+: ', '', str(e))}") from e
    conf = folder / "automation.conf"
    kept = None
    if conf.exists() and not force:
        # Without --force an existing file stays, so it has to work as it is
        try:
            kept = automation_conf.read(conf)
        except automation_conf.ConfError as e:
            raise Refused(f"automation.conf: {e}. Correct the file, or rewrite it with --force.") from e
    final = kept or settings
    launcher = LAUNCHER.read_bytes()

    lock = locker(folder)
    try:
        created, replaced, removed = [], [], []
        for name in SCRIPT_NAMES:
            path = folder / name
            if not path.exists():
                created.append(name)
            elif path.read_bytes() != launcher:
                replaced.append(name)
        if not conf.exists():
            created.append(conf.name)
        elif force and conf.read_bytes() != conf_text.encode("utf-8"):
            replaced.append(conf.name)
        if (folder / "pipeline").exists():
            removed.append("pipeline")
        if not (created or replaced or removed):
            print(f"{folder} is already installed: nothing to do.")
            _note_kept_conf(kept, settings)
            _note_branch_mismatch(folder, final["branch"])
            return 0

        backup = _new_backup_folder(folder)
        backup.mkdir()
        for name in replaced:
            shutil.copy2(folder / name, backup / name)
        for name in removed:
            shutil.copytree(folder / name, backup / name, symlinks=True)
        manifest = {"folder": str(folder), "created": created, "replaced": replaced, "removed": removed}
        (backup / "backup.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        # Said before anything changes, so that a crash from here on still names the way back
        undo = " ".join(
            shlex.quote(part)
            for part in ("python3", str(HERE / "install.py"), "--folder", str(folder), "--restore", backup.name)
        )
        print(f"Backed up into {backup.name}. Undo with: {undo}")

        for name in created + replaced:
            if name in SCRIPT_NAMES:
                _put(folder / name, launcher, 0o755)
            else:
                _put(folder / name, conf_text.encode("utf-8"), 0o644)
        for name in removed:
            shutil.rmtree(folder / name)
        (folder / "runs").mkdir(exist_ok=True)
    finally:
        lock.close()

    print(f"Installed into {folder} ({final['side']}, following {final['branch']}).")
    _note_kept_conf(kept, settings)
    _note_branch_mismatch(folder, final["branch"])
    return 0
