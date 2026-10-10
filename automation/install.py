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


def check(folder, which=shutil.which, locker=lock_release):
    """Say whether folder is ready for releases: 0 if it is, 1 if not. Changes nothing."""
    folder = Path(folder).resolve()
    problems = []

    def report(ok, text):
        print(("ok      " if ok else "PROBLEM ") + text)
        if not ok:
            problems.append(text)

    try:
        packs = check_folder(folder)
    except Refused as e:
        report(False, str(e))
        print("Not ready: 1 problem(s).")
        return 1
    report(True, f"automation folder with {len(packs)} pack checkout(s): {', '.join(packs)}")

    settings = None
    try:
        settings = automation_conf.read(folder / "automation.conf")
        report(True, "automation.conf: " + ", ".join(f"{k}={v}" for k, v in settings.items()))
    except automation_conf.ConfError as e:
        report(False, f"automation.conf: {e}")

    checkout = folder / "ResourcePackScripts"
    # As the launcher reads it: the full name, so a tag can't confuse it
    head = git(checkout, "symbolic-ref", "--quiet", "HEAD") or ""
    current = head[len("refs/heads/"):] if head.startswith("refs/heads/") else "no branch"
    if settings:
        branch = settings["branch"]
        report(current == branch, f"ResourcePackScripts is on {current} (automation.conf: {branch})")
        # What the launcher refuses: commits made here that GitHub doesn't have. No fetch, so as of the last one
        ahead = git(checkout, "rev-list", "--count", f"refs/remotes/origin/{branch}..HEAD")
        if ahead is None:
            report(False, f"GitHub's {branch} has never been fetched into ResourcePackScripts")
        elif ahead == "0":
            report(True, f"ResourcePackScripts has no commits that GitHub's {branch} lacks (as of the last fetch)")
        else:
            report(
                False,
                f"ResourcePackScripts has {ahead} commit(s) that GitHub's {branch} doesn't: made on the server"
                " (they need a pull request), or GitHub's history was rewritten (reset the checkout to it)",
            )
    # --no-optional-locks: a plain status rewrites .git/index, which could make a running release's merge fail
    edits = git(checkout, "--no-optional-locks", "status", "--porcelain")
    if edits is None:
        report(False, "git status failed in ResourcePackScripts")
    else:
        report(edits == "", "ResourcePackScripts has no local edits" if edits == "" else f"ResourcePackScripts has local edits:\n{edits}")

    launcher = LAUNCHER.read_bytes()
    for name in SCRIPT_NAMES:
        path = folder / name
        report(path.is_file() and path.read_bytes() == launcher, f"{name} is the launcher")
    # What the launchers hand over to: without it every release stops with exit 2
    for name in SCRIPT_NAMES:
        report((checkout / "automation" / "scripts" / name).is_file(), f"ResourcePackScripts has automation/scripts/{name}")
    if settings and settings["wrapper"] == "yes":
        entry = checkout / "automation" / "pipeline" / "run"
        report(entry.is_file() and os.access(entry, os.X_OK), "ResourcePackScripts has an executable automation/pipeline/run")
    for tool in TOOLS:
        report(which(tool) is not None, f"{tool} is on PATH")

    if (folder / "runs" / ".lock").exists():
        try:
            locker(folder).close()
            report(True, "no release is running")
        except LockHeld:
            report(False, "a release is running")
    else:
        report(True, "no release is running")

    print("Ready." if not problems else f"Not ready: {len(problems)} problem(s).")
    return 0 if not problems else 1


def restore(folder, backup, locker=lock_release):
    """Put back what an install replaced or removed, and remove what it created."""
    folder = Path(folder).resolve()
    backup = Path(backup)
    if not backup.is_absolute():
        backup = folder / backup
    manifest_path = backup / "backup.json"
    if not manifest_path.is_file():
        raise Refused(f"{backup} isn't a backup made by install.py: it has no backup.json")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except ValueError as e:  # JSONDecodeError and UnicodeDecodeError both are
        raise Refused(f"{manifest_path} isn't a manifest written by install.py: {e}") from e
    if not isinstance(manifest, dict) or not all(
        isinstance(manifest.get(key, []), list) for key in ("created", "replaced", "removed")
    ):
        raise Refused(f"{manifest_path} isn't a manifest written by install.py")
    if manifest.get("folder") != str(folder):
        # Test's backup restored into production would bring test's scripts back there
        raise Refused(f"{backup.name} was made for {manifest.get('folder')}, not for {folder}")
    created = manifest.get("created", [])
    replaced = manifest.get("replaced", [])
    removed = manifest.get("removed", [])
    # Only what install itself writes or removes: restore deletes before it copies back
    for name in list(created) + list(replaced):
        if name not in SCRIPT_NAMES + ("automation.conf",):
            raise Refused(f"{manifest_path} names {name!r}, which install.py never writes")
    for name in removed:
        if name != "pipeline":
            raise Refused(f"{manifest_path} names {name!r}, which install.py never removes")
    # Everything to put back must be there, as install made it, before anything is touched
    for name in list(replaced) + list(removed):
        path = backup / name
        plain = path.is_dir() if name == "pipeline" else path.is_file()
        if path.is_symlink() or not plain:
            raise Refused(f"{backup.name} lacks {name}, or holds something else under that name, so it can't be restored")
    # And the folder must hold what install left: a symlinked pipeline would stop restore halfway
    _check_shapes(folder)

    lock = locker(folder)
    try:
        for name in created:
            (folder / name).unlink(missing_ok=True)
        for name in replaced:
            source = backup / name
            _put(folder / name, source.read_bytes(), source.stat().st_mode & 0o777)
        for name in removed:
            if (folder / name).exists():
                shutil.rmtree(folder / name)
            shutil.copytree(backup / name, folder / name, symlinks=True)
    finally:
        lock.close()
    print(f"Restored {folder} from {backup.name}.")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Install the release launchers into an automation folder, check one, or restore a backup."
    )
    parser.add_argument("--side", choices=sorted(automation_conf.DEFAULTS), help="install for this side")
    parser.add_argument("--folder", type=Path, default=Path("."), help="the automation folder (default: here)")
    parser.add_argument("--branch", help="the branch to follow (default: development for test, master for production)")
    parser.add_argument("--force", action="store_true", help="rewrite an existing automation.conf")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="say whether the folder is ready; change nothing")
    mode.add_argument("--restore", type=Path, metavar="BACKUP", help="put back what an install replaced")
    args = parser.parse_args(argv)
    if not (args.check or args.restore or args.side):
        parser.error("--side is required to install")
    try:
        if args.check:
            return check(args.folder)
        if args.restore:
            return restore(args.folder, args.restore)
        return install(args.folder, args.side, args.branch, args.force)
    except LockHeld:
        print("A release is running in this folder. Run install.py again once it has finished.", file=sys.stderr)
        return LOCK_HELD
    except Refused as e:
        print(f"install.py: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
