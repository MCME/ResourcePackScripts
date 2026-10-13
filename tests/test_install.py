"""Tests for automation/install.py: installing the launchers into an automation folder.

Plain unittest, so WSL can run it without pytest. The release lock is faked,
except in the Linux-only RealLock tests, which take a real flock.
"""

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "automation"))

import automation_conf  # noqa: E402
import install  # noqa: E402

LAUNCHER_BYTES = (REPO_ROOT / "automation" / "launcher.sh").read_bytes()

GIT_ENV = dict(
    os.environ,
    GIT_AUTHOR_NAME="test",
    GIT_AUTHOR_EMAIL="test@example.com",
    GIT_COMMITTER_NAME="test",
    GIT_COMMITTER_EMAIL="test@example.com",
)
# The developer's own git config never reaches these tests
ISOLATED_GIT = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"} if os.name == "posix" else {}
GIT_ENV.update(ISOLATED_GIT)


def git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, env=GIT_ENV, check=True, capture_output=True)


class FakeLock:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def free_lock(folder):
    return FakeLock()


def held_lock(folder):
    raise install.LockHeld()


def all_present(tool):
    return f"/usr/bin/{tool}"


def snapshot(folder, skip=("ResourcePackScripts/.git",)):
    """Every file under folder as bytes, by its path relative to folder."""
    files = {}
    for path in sorted(Path(folder).rglob("*")):
        rel = path.relative_to(folder).as_posix()
        if path.is_file() and not any(rel == s or rel.startswith(s + "/") for s in skip):
            files[rel] = path.read_bytes()
    return files


class InstallerTest(unittest.TestCase):
    """A throwaway automation folder as the server has it before the install."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        patcher = mock.patch.dict(os.environ, ISOLATED_GIT)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.folder = self.tmp / "resourcePackAutomation"
        checkout = self.folder / "ResourcePackScripts"
        checkout.mkdir(parents=True)
        git("init", "-q", "-b", "development", cwd=checkout)
        git("remote", "add", "origin", "https://github.com/MCME/ResourcePackScripts.git", cwd=checkout)
        (checkout / "README.md").write_text("checkout\n")
        # The launcher the folder installs, and what it hands over to, which install and --check look for
        (checkout / "automation" / "scripts").mkdir(parents=True)
        for name in install.SCRIPT_NAMES:
            (checkout / "automation" / "scripts" / name).write_text("# a release script\n")
        (checkout / "automation" / "launcher.sh").write_bytes(LAUNCHER_BYTES)
        (checkout / "automation" / "pipeline").mkdir()
        (checkout / "automation" / "pipeline" / "run.sh").write_text("# the wrapper\n")
        (checkout / "automation" / "pipeline" / "rp-release.py").write_text("# the wrapper's logger\n")
        git("add", "-A", cwd=checkout)
        git("commit", "-q", "-m", "checkout", cwd=checkout)
        # As after a fetch: GitHub's development is where the checkout is
        git("update-ref", "refs/remotes/origin/development", "HEAD", cwd=checkout)
        for pack in ("Human-Sodium", "Rohan-Vanilla"):
            (self.folder / pack).mkdir()
            (self.folder / pack / "pack.mcmeta").write_text('{"pack": {"pack_format": 88}}')
        (self.folder / "releaseVanillaSodium.sh").write_text("# hand-edited copy\n")
        (self.folder / "releaseGeneral.sh").write_text("# hand-edited copy\n")
        (self.folder / "pipeline").mkdir()
        (self.folder / "pipeline" / "wrapper.py").write_text("# the old wrapper\n")
        (self.folder / "Footprints").mkdir()
        (self.folder / "Footprints" / "activator_rail.png").write_bytes(b"png")
        (self.folder / "release").mkdir()
        (self.folder / "release" / "Human-Sodium.zip").write_bytes(b"zip")
        self.before = snapshot(self.folder)

    def run_install(self, side="test", **kwargs):
        out = io.StringIO()
        with redirect_stdout(out):
            code = install.install(self.folder, side, locker=free_lock, **kwargs)
        return code, out.getvalue()

    def run_main(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = install.main(list(args))
        return code, out.getvalue(), err.getvalue()

    def backups(self):
        return sorted(self.folder.glob("pre-automation-backup-*"))


class Install(InstallerTest):
    def test_writes_the_launcher_under_every_script_name(self):
        self.assertEqual(self.run_install()[0], 0)
        for name in install.SCRIPT_NAMES:
            with self.subTest(name=name):
                self.assertEqual((self.folder / name).read_bytes(), LAUNCHER_BYTES)
                if os.name == "posix":
                    self.assertTrue(os.access(self.folder / name, os.X_OK))

    def test_writes_the_sides_settings(self):
        self.run_install("production")
        self.assertEqual(
            automation_conf.read(self.folder / "automation.conf"), automation_conf.DEFAULTS["production"]
        )

    def test_takes_a_branch_other_than_the_default(self):
        self.run_install(branch="release-2026")
        self.assertEqual(automation_conf.read(self.folder / "automation.conf")["branch"], "release-2026")

    def test_removes_the_old_wrapper_and_creates_runs(self):
        self.run_install()
        self.assertFalse((self.folder / "pipeline").exists())
        self.assertTrue((self.folder / "runs").is_dir())

    def test_backs_up_everything_it_replaces_or_removes(self):
        self.run_install()
        [backup] = self.backups()
        self.assertEqual((backup / "releaseVanillaSodium.sh").read_text(), "# hand-edited copy\n")
        self.assertEqual((backup / "releaseGeneral.sh").read_text(), "# hand-edited copy\n")
        self.assertEqual((backup / "pipeline" / "wrapper.py").read_text(), "# the old wrapper\n")
        self.assertEqual(
            json.loads((backup / "backup.json").read_text()),
            {
                "folder": str(self.folder.resolve()),
                "created": ["releaseDynmap.sh", "automation.conf"],
                "replaced": ["releaseVanillaSodium.sh", "releaseGeneral.sh"],
                "removed": ["pipeline"],
            },
        )

    def test_leaves_packs_footprints_and_built_zips_alone(self):
        self.run_install()
        untouched = ("Human-Sodium", "Rohan-Vanilla", "Footprints", "release", "ResourcePackScripts")

        def under_untouched(files):
            return {rel: data for rel, data in files.items() if rel.split("/")[0] in untouched}

        # Nothing changed, removed or added there
        self.assertEqual(under_untouched(snapshot(self.folder)), under_untouched(self.before))

    def test_installing_twice_changes_nothing(self):
        self.run_install()
        installed = snapshot(self.folder)
        code, out = self.run_install()
        self.assertEqual(code, 0)
        self.assertIn("already installed", out)
        self.assertEqual(snapshot(self.folder), installed)
        self.assertEqual(len(self.backups()), 1)

    def test_keeps_an_existing_automation_conf(self):
        custom = automation_conf.render(dict(automation_conf.DEFAULTS["test"], branch="feature-x"))
        (self.folder / "automation.conf").write_text(custom)
        self.run_install()
        self.assertEqual((self.folder / "automation.conf").read_text(), custom)

    def test_says_when_the_automation_conf_it_keeps_differs(self):
        self.run_install()
        code, out = self.run_install("production")
        self.assertEqual(code, 0)
        self.assertIn("automation.conf was kept as it is (side=test, branch=development", out)
        self.assertIn("--force", out)

    def test_force_rewrites_automation_conf_after_backing_it_up(self):
        custom = automation_conf.render(dict(automation_conf.DEFAULTS["test"], branch="feature-x"))
        (self.folder / "automation.conf").write_text(custom)
        self.run_install(force=True)
        self.assertEqual(automation_conf.read(self.folder / "automation.conf")["branch"], "development")
        [backup] = self.backups()
        self.assertEqual((backup / "automation.conf").read_text(), custom)

    def test_force_replaces_an_automation_conf_that_is_not_utf8(self):
        # The refusal without --force recommends --force, so it has to work on such a file
        (self.folder / "automation.conf").write_bytes(b"# caf\xe9\nside=test\n")
        self.assertEqual(self.run_install(force=True)[0], 0)
        self.assertEqual(automation_conf.read(self.folder / "automation.conf"), automation_conf.DEFAULTS["test"])
        [backup] = self.backups()
        self.assertEqual((backup / "automation.conf").read_bytes(), b"# caf\xe9\nside=test\n")

    def test_releases_the_lock(self):
        lock = FakeLock()
        with redirect_stdout(io.StringIO()):
            install.install(self.folder, "test", locker=lambda folder: lock)
        self.assertTrue(lock.closed)

    def test_releases_the_lock_when_already_installed(self):
        self.run_install()
        lock = FakeLock()
        with redirect_stdout(io.StringIO()):
            install.install(self.folder, "test", locker=lambda folder: lock)
        self.assertTrue(lock.closed)

    def test_the_backup_is_complete_before_the_first_change(self):
        # Whichever change comes first fails: backup.json, the copies and the way back must already be there
        out = io.StringIO()
        with mock.patch.object(install, "_put", side_effect=OSError("disk full")), \
                mock.patch.object(install.shutil, "rmtree", side_effect=OSError("disk full")):
            with self.assertRaises(OSError), redirect_stdout(out):
                install.install(self.folder, "test", locker=free_lock)
        [backup] = self.backups()
        manifest = json.loads((backup / "backup.json").read_text())
        self.assertEqual(manifest["replaced"], ["releaseVanillaSodium.sh", "releaseGeneral.sh"])
        self.assertEqual(manifest["removed"], ["pipeline"])
        self.assertEqual((backup / "releaseGeneral.sh").read_text(), "# hand-edited copy\n")
        self.assertEqual((backup / "pipeline" / "wrapper.py").read_text(), "# the old wrapper\n")
        self.assertIn(f"Backed up into {backup.name}. Undo with: ", out.getvalue())
        self.assertEqual(snapshot(self.folder, skip=("ResourcePackScripts/.git", backup.name)), self.before)

    def test_a_failed_write_leaves_no_temporary_file(self):
        with mock.patch.object(install.os, "replace", side_effect=OSError("disk full")):
            with self.assertRaises(OSError), redirect_stdout(io.StringIO()):
                install.install(self.folder, "test", locker=free_lock)
        self.assertEqual(list(self.folder.glob(".*.install-tmp")), [])

    @unittest.skipUnless(os.name == "posix", "symlinks need extra rights on Windows")
    def test_keeps_symlinks_inside_pipeline_as_links(self):
        (self.folder / "pipeline" / "venv").symlink_to(self.tmp)
        self.run_install()
        [backup] = self.backups()
        self.assertTrue((backup / "pipeline" / "venv").is_symlink())

    def test_says_nothing_about_the_branch_when_it_matches(self):
        self.assertNotIn("Note:", self.run_install("test")[1])

    def test_warns_about_the_branch_when_already_installed(self):
        self.run_install("production")
        code, out = self.run_install("production")
        self.assertIn("already installed", out)
        self.assertIn("ResourcePackScripts is on development, but this folder follows master", out)

    @unittest.skipUnless(os.name == "posix", "replacing a file that is open needs POSIX semantics")
    def test_a_release_reading_the_old_script_goes_on_reading_it(self):
        # sh reads a script as it runs, so the install must replace the file, not rewrite it
        with open(self.folder / "releaseGeneral.sh", "rb") as running:
            self.run_install()
            self.assertEqual(running.read(), b"# hand-edited copy\n")
        self.assertEqual((self.folder / "releaseGeneral.sh").read_bytes(), LAUNCHER_BYTES)

    def test_a_full_install_reports_the_kept_side_and_branch(self):
        (self.folder / "automation.conf").write_text(automation_conf.render(automation_conf.DEFAULTS["production"]))
        code, out = self.run_install("test")
        self.assertEqual(code, 0)
        self.assertIn("(production, following master)", out)
        self.assertIn("automation.conf was kept as it is (side=production", out)

    def test_warns_when_the_checkout_is_on_another_branch(self):
        code, out = self.run_install("production")
        self.assertEqual(code, 0)
        self.assertIn("ResourcePackScripts is on development, but this folder follows master", out)

    def test_installs_the_launcher_of_the_folders_own_checkout(self):
        # Not the one next to the install.py that runs: with --folder they can differ
        checkout = self.folder / "ResourcePackScripts"
        (checkout / "automation" / "launcher.sh").write_bytes(b"#!/bin/sh\n# the checkout's launcher\n")
        git("commit", "-q", "-am", "another launcher", cwd=checkout)
        git("update-ref", "refs/remotes/origin/development", "HEAD", cwd=checkout)
        self.run_install()
        self.assertEqual((self.folder / "releaseGeneral.sh").read_bytes(), b"#!/bin/sh\n# the checkout's launcher\n")

    def test_the_undo_command_runs_the_folders_own_install_py(self):
        code, out = self.run_install()
        self.assertIn(str(self.folder.resolve() / "ResourcePackScripts" / "automation" / "install.py"), out)

    @unittest.skipUnless(os.name == "posix", "symlinks need extra rights on Windows")
    def test_never_writes_through_a_symlink_left_at_the_temporary_name(self):
        outside = self.tmp / "outside.txt"
        outside.write_text("not install.py's\n")
        (self.folder / ".releaseGeneral.sh.install-tmp").symlink_to(outside)
        self.run_install()
        self.assertEqual(outside.read_text(), "not install.py's\n")
        self.assertEqual((self.folder / "releaseGeneral.sh").read_bytes(), LAUNCHER_BYTES)
        self.assertFalse(os.path.lexists(self.folder / ".releaseGeneral.sh.install-tmp"))


class Refusals(InstallerTest):
    def refused(self, side="test", **kwargs):
        """The Refused install, which changed nothing and never took the release lock."""
        before = snapshot(self.folder)

        def no_lock(folder):
            self.fail("a refusal took the release lock")

        with self.assertRaises(install.Refused) as caught, redirect_stdout(io.StringIO()):
            install.install(self.folder, side, locker=no_lock, **kwargs)
        self.assertEqual(snapshot(self.folder), before)
        return caught.exception

    def test_refuses_a_folder_without_a_resourcepackscripts_checkout(self):
        (self.folder / "ResourcePackScripts").rename(self.tmp / "moved-away")
        self.refused()

    def test_refuses_a_checkout_of_another_repository(self):
        git(
            "remote", "set-url", "origin", "https://github.com/someone/ResourcePackScripts-fork.git",
            cwd=self.folder / "ResourcePackScripts",
        )
        self.refused()

    def test_says_why_git_cannot_read_the_origin(self):
        git("remote", "remove", "origin", cwd=self.folder / "ResourcePackScripts")
        self.assertIn("No such remote", str(self.refused()))

    def test_accepts_every_remote_form_of_the_repository(self):
        for url in (
            "https://github.com/MCME/ResourcePackScripts",
            "https://github.com/MCME/ResourcePackScripts.git",
            "https://github.com/mcme/resourcepackscripts.git",
            "git@github.com:MCME/ResourcePackScripts.git",
            "ssh://git@github.com/MCME/ResourcePackScripts.git",
            "https://x-access-token:abc@github.com/MCME/ResourcePackScripts.git",
        ):
            with self.subTest(url=url):
                git("remote", "set-url", "origin", url, cwd=self.folder / "ResourcePackScripts")
                self.assertEqual(install.check_folder(self.folder), ["Human-Sodium", "Rohan-Vanilla"])

    def test_refuses_other_repositories(self):
        for url in (
            "https://github.com/someone/ResourcePackScripts.git",
            "https://github.com/MCME/ResourcePackScripts-fork.git",
            "https://notgithub.com/MCME/ResourcePackScripts.git",
            # github.com as a path segment, not the host
            "https://evil.example/github.com/MCME/ResourcePackScripts.git",
            "file:///srv/mirror/github.com/MCME/ResourcePackScripts.git",
            "/srv/mirror/github.com/MCME/ResourcePackScripts.git",
        ):
            with self.subTest(url=url):
                git("remote", "set-url", "origin", url, cwd=self.folder / "ResourcePackScripts")
                with self.assertRaises(install.Refused):
                    install.check_folder(self.folder)

    def test_never_shows_the_origins_credentials(self):
        git(
            "remote", "set-url", "origin", "https://x-access-token:SECRET@gitlab.com/someone/scripts.git",
            cwd=self.folder / "ResourcePackScripts",
        )
        message = str(self.refused())
        self.assertNotIn("SECRET", message)
        self.assertIn("<credentials>@gitlab.com", message)

    def test_refuses_to_run_as_root(self):
        # What it wrote would belong to root, and the launcher, run as the servers' user, couldn't open runs/.lock
        with mock.patch.object(install.os, "geteuid", return_value=0, create=True):
            self.assertIn("not as root", str(self.refused()))

    def test_refuses_a_folder_without_pack_checkouts(self):
        for pack in ("Human-Sodium", "Rohan-Vanilla"):
            (self.folder / pack).rename(self.tmp / pack)
        self.refused()

    def test_refuses_a_branch_name_that_would_need_quoting(self):
        # Named by its option: a line number would point into install's own text
        self.assertIn("--branch '-x'", str(self.refused(branch="-x")))

    def test_refuses_to_keep_an_invalid_automation_conf(self):
        # Without --force the file would stay, and every release would stop on it
        (self.folder / "automation.conf").write_text("side=staging\n")
        self.assertIn("--force", str(self.refused()))

    def test_refuses_a_folder_where_automation_conf_should_be(self):
        (self.folder / "automation.conf").mkdir()
        self.assertIn("not a plain file", str(self.refused(force=True)))

    @unittest.skipUnless(os.name == "posix", "symlinks need extra rights on Windows")
    def test_refuses_a_script_name_that_is_a_symlink(self):
        # Writing through it would change a file outside the folder
        outside = self.tmp / "elsewhere.sh"
        outside.write_text("# someone else's script\n")
        (self.folder / "releaseGeneral.sh").unlink()
        (self.folder / "releaseGeneral.sh").symlink_to(outside)
        self.assertIn("a symlink", str(self.refused()))
        self.assertEqual(outside.read_text(), "# someone else's script\n")

    @unittest.skipUnless(os.name == "posix", "symlinks need extra rights on Windows")
    def test_refuses_a_pipeline_that_is_a_symlink(self):
        # rmtree can't remove it, and restore couldn't put it back
        elsewhere = self.tmp / "wrapper-elsewhere"
        (self.folder / "pipeline").rename(elsewhere)
        (self.folder / "pipeline").symlink_to(elsewhere)
        self.assertIn("pipeline is a symlink", str(self.refused()))

    def test_changes_nothing_while_a_release_is_running(self):
        with self.assertRaises(install.LockHeld):
            install.install(self.folder, "test", locker=held_lock)
        self.assertEqual(snapshot(self.folder), self.before)

    def test_refuses_a_checkout_without_the_launcher(self):
        # A checkout from before the automation: there is nothing to install yet
        checkout = self.folder / "ResourcePackScripts"
        git("rm", "-q", "automation/launcher.sh", cwd=checkout)
        git("commit", "-q", "-m", "no launcher", cwd=checkout)
        self.assertIn("no automation/launcher.sh", str(self.refused()))


class Check(InstallerTest):
    def run_check(self, which=all_present, locker=free_lock):
        out = io.StringIO()
        with redirect_stdout(out):
            code = install.check(self.folder, which=which, locker=locker)
        return code, out.getvalue()

    def test_an_installed_folder_is_ready(self):
        self.run_install()
        code, out = self.run_check()
        self.assertEqual(code, 0, out)
        self.assertNotIn("PROBLEM", out)

    def test_a_folder_before_the_install_is_not_ready(self):
        code, out = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("PROBLEM automation.conf", out)
        self.assertIn("PROBLEM releaseDynmap.sh is the launcher", out)

    def test_changes_nothing(self):
        before = snapshot(self.folder)
        self.run_check()
        self.assertEqual(snapshot(self.folder), before)

    def test_reports_a_missing_tool(self):
        self.run_install()
        code, out = self.run_check(which=lambda tool: None if tool == "7z" else f"/usr/bin/{tool}")
        self.assertEqual(code, 1)
        self.assertIn("PROBLEM 7z is on PATH", out)

    def test_reports_local_edits_in_the_checkout(self):
        self.run_install()
        (self.folder / "ResourcePackScripts" / "README.md").write_text("edited on the server\n")
        code, out = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("local edits", out)

    def test_reports_the_wrong_branch(self):
        self.run_install()
        git("checkout", "-q", "-b", "hotfix", cwd=self.folder / "ResourcePackScripts")
        code, out = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("hotfix", out)

    def test_reports_a_checkout_without_the_wrapper(self):
        self.run_install()
        checkout = self.folder / "ResourcePackScripts"
        git("rm", "-q", "automation/pipeline/run.sh", cwd=checkout)
        git("commit", "-q", "-m", "no wrapper", cwd=checkout)
        git("update-ref", "refs/remotes/origin/development", "HEAD", cwd=checkout)
        code, out = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("PROBLEM ResourcePackScripts has the pipeline wrapper", out)

    def test_reports_a_checkout_without_the_launcher(self):
        self.run_install()
        checkout = self.folder / "ResourcePackScripts"
        git("rm", "-q", "automation/launcher.sh", cwd=checkout)
        git("commit", "-q", "-m", "no launcher", cwd=checkout)
        git("update-ref", "refs/remotes/origin/development", "HEAD", cwd=checkout)
        code, out = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("PROBLEM ResourcePackScripts has no automation/launcher.sh", out)
        self.assertIn("PROBLEM releaseGeneral.sh is the launcher", out)

    def test_shows_each_local_edit_with_its_status(self):
        # git's two status columns: " M" is a change not staged
        self.run_install()
        (self.folder / "ResourcePackScripts" / "README.md").write_text("edited on the server\n")
        code, out = self.run_check()
        self.assertIn("\n M README.md", out)

    def test_leaves_a_folder_without_runs_alone(self):
        # Before the install there is no runs/.lock to probe, so check must not create one
        def no_lock(folder):
            self.fail("check took the release lock")

        self.run_check(locker=no_lock)
        self.assertFalse((self.folder / "runs").exists())

    def test_reports_a_release_script_the_checkout_lacks(self):
        self.run_install()
        checkout = self.folder / "ResourcePackScripts"
        git("rm", "-q", "automation/scripts/releaseDynmap.sh", cwd=checkout)
        git("commit", "-q", "-m", "no dynmap", cwd=checkout)
        git("update-ref", "refs/remotes/origin/development", "HEAD", cwd=checkout)
        code, out = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("PROBLEM ResourcePackScripts has automation/scripts/releaseDynmap.sh", out)

    def test_reports_commits_github_does_not_have(self):
        self.run_install()
        checkout = self.folder / "ResourcePackScripts"
        (checkout / "local.txt").write_text("a commit made on the server\n")
        git("add", "local.txt", cwd=checkout)
        git("commit", "-q", "-m", "server-side commit", cwd=checkout)
        code, out = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("PROBLEM ResourcePackScripts has 1 commit(s) that GitHub's development doesn't", out)

    def test_does_not_rewrite_the_checkouts_index(self):
        # A plain git status refreshes .git/index, which could make a running release's merge fail
        self.run_install()
        checkout = self.folder / "ResourcePackScripts"
        readme = checkout / "README.md"
        stat = readme.stat()
        os.utime(readme, (stat.st_atime, stat.st_mtime + 100))  # a stale stat: plain status would rewrite the index
        index = (checkout / ".git" / "index").read_bytes()
        self.run_check()
        self.assertEqual((checkout / ".git" / "index").read_bytes(), index)

    def test_reports_a_file_added_to_the_checkout(self):
        # As the launcher sees it, whatever the server's git config says
        self.run_install()
        checkout = self.folder / "ResourcePackScripts"
        git("config", "status.showUntrackedFiles", "no", cwd=checkout)
        (checkout / "automation" / "scripts" / "releaseExtra.sh").write_text("echo unreviewed\n")
        code, out = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("releaseExtra.sh", out)

    def test_reports_running_as_root(self):
        self.run_install()
        with mock.patch.object(install.os, "geteuid", return_value=0, create=True):
            code, out = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("PROBLEM --check runs as root", out)

    @unittest.skipUnless(os.name == "posix" and os.geteuid() != 0, "file modes are POSIX, and root ignores them")
    def test_reports_a_lock_file_the_launcher_could_not_write(self):
        # What a sudo install leaves behind: every release would stop with "Permission denied"
        self.run_install()
        lock = self.folder / "runs" / ".lock"
        lock.write_text("")
        lock.chmod(0o444)
        self.addCleanup(lock.chmod, 0o644)
        code, out = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("PROBLEM runs/.lock can be written", out)

    def test_reports_a_lock_it_cannot_open(self):
        self.run_install()
        (self.folder / "runs" / ".lock").write_text("")

        def denied(folder):
            raise PermissionError(13, "Permission denied")

        code, out = self.run_check(locker=denied)
        self.assertEqual(code, 1)
        self.assertIn("PROBLEM runs/.lock can't be opened: Permission denied", out)

    def test_reports_a_running_release(self):
        self.run_install()
        (self.folder / "runs" / ".lock").write_text("")
        code, out = self.run_check(locker=held_lock)
        self.assertEqual(code, 1)
        self.assertIn("PROBLEM a release is running", out)


class Restore(InstallerTest):
    def test_puts_back_what_the_install_replaced_and_removed(self):
        self.run_install()
        [backup] = self.backups()
        with redirect_stdout(io.StringIO()):
            self.assertEqual(install.restore(self.folder, backup, locker=free_lock), 0)
        restored = snapshot(self.folder, skip=("ResourcePackScripts/.git", "runs", backup.name))
        self.assertEqual(restored, self.before)

    def test_takes_the_backup_by_its_name_inside_the_folder(self):
        self.run_install()
        [backup] = self.backups()
        with redirect_stdout(io.StringIO()):
            self.assertEqual(install.restore(self.folder, Path(backup.name), locker=free_lock), 0)
        self.assertEqual((self.folder / "releaseGeneral.sh").read_text(), "# hand-edited copy\n")

    def test_refuses_a_folder_that_is_not_a_backup(self):
        with self.assertRaises(install.Refused):
            install.restore(self.folder, self.folder / "Footprints", locker=free_lock)

    def test_refuses_a_manifest_naming_a_path_outside_the_folder(self):
        forged = self.folder / "pre-automation-backup-forged"
        forged.mkdir()
        (forged / "backup.json").write_text(
            json.dumps({"folder": str(self.folder.resolve()), "created": ["../outside.txt"], "replaced": [], "removed": []})
        )
        with self.assertRaises(install.Refused):
            install.restore(self.folder, forged, locker=free_lock)

    def test_refuses_a_manifest_naming_a_pack_checkout(self):
        # restore removes before it copies back, so it may only touch what install wrote
        forged = self.folder / "pre-automation-backup-forged"
        (forged / "Human-Sodium").mkdir(parents=True)
        (forged / "backup.json").write_text(
            json.dumps({"folder": str(self.folder.resolve()), "created": [], "replaced": [], "removed": ["Human-Sodium"]})
        )
        before = snapshot(self.folder)
        with self.assertRaises(install.Refused):
            install.restore(self.folder, forged, locker=free_lock)
        self.assertEqual(snapshot(self.folder), before)

    def test_refuses_a_backup_that_lacks_a_file_before_touching_anything(self):
        self.run_install()
        [backup] = self.backups()
        (backup / "releaseGeneral.sh").unlink()
        installed = snapshot(self.folder)
        with self.assertRaises(install.Refused):
            install.restore(self.folder, backup, locker=free_lock)
        self.assertEqual(snapshot(self.folder), installed)

    def test_refuses_a_backup_made_for_another_folder(self):
        self.run_install()
        [backup] = self.backups()
        manifest = json.loads((backup / "backup.json").read_text())
        manifest["folder"] = str(self.tmp / "elsewhere")
        (backup / "backup.json").write_text(json.dumps(manifest))
        with self.assertRaises(install.Refused):
            install.restore(self.folder, backup, locker=free_lock)

    def test_undoes_an_install_that_died_halfway(self):
        # What the backup is for: the install stopped with the launchers written and pipeline/ still there
        with mock.patch.object(install.shutil, "rmtree", side_effect=OSError("disk trouble")):
            with self.assertRaises(OSError), redirect_stdout(io.StringIO()):
                install.install(self.folder, "test", locker=free_lock)
        [backup] = self.backups()
        with redirect_stdout(io.StringIO()):
            self.assertEqual(install.restore(self.folder, backup, locker=free_lock), 0)
        self.assertEqual(snapshot(self.folder, skip=("ResourcePackScripts/.git", "runs", backup.name)), self.before)

    def test_changes_nothing_while_a_release_is_running(self):
        self.run_install()
        [backup] = self.backups()
        installed = snapshot(self.folder)
        with self.assertRaises(install.LockHeld), redirect_stdout(io.StringIO()):
            install.restore(self.folder, backup, locker=held_lock)
        self.assertEqual(snapshot(self.folder), installed)

    def test_refusals_never_take_the_lock(self):
        def no_lock(folder):
            self.fail("a refusal took the release lock")

        forged = self.folder / "pre-automation-backup-forged"
        forged.mkdir()
        (forged / "backup.json").write_text(json.dumps({"folder": str(self.folder.resolve()), "removed": ["Footprints"]}))
        with self.assertRaises(install.Refused), redirect_stdout(io.StringIO()):
            install.restore(self.folder, forged, locker=no_lock)

    def test_refuses_a_manifest_that_is_not_an_object(self):
        forged = self.folder / "pre-automation-backup-forged"
        forged.mkdir()
        (forged / "backup.json").write_text("[]")
        with self.assertRaises(install.Refused), redirect_stdout(io.StringIO()):
            install.restore(self.folder, forged, locker=free_lock)

    def test_refuses_a_manifest_that_is_not_json(self):
        forged = self.folder / "pre-automation-backup-forged"
        forged.mkdir()
        (forged / "backup.json").write_text('{"folder": ')
        with self.assertRaises(install.Refused), redirect_stdout(io.StringIO()):
            install.restore(self.folder, forged, locker=free_lock)

    def test_refuses_a_backup_whose_pipeline_is_not_a_folder(self):
        # The live pipeline/ would be deleted before the copy back failed
        forged = self.folder / "pre-automation-backup-forged"
        forged.mkdir()
        (forged / "pipeline").write_text("not a folder")
        (forged / "backup.json").write_text(json.dumps({"folder": str(self.folder.resolve()), "removed": ["pipeline"]}))
        before = snapshot(self.folder)
        with self.assertRaises(install.Refused), redirect_stdout(io.StringIO()):
            install.restore(self.folder, forged, locker=free_lock)
        self.assertEqual(snapshot(self.folder), before)

    def test_refuses_a_backup_holding_a_folder_where_a_file_was(self):
        self.run_install()
        [backup] = self.backups()
        (backup / "releaseGeneral.sh").unlink()
        (backup / "releaseGeneral.sh").mkdir()
        installed = snapshot(self.folder)
        with self.assertRaises(install.Refused), redirect_stdout(io.StringIO()):
            install.restore(self.folder, backup, locker=free_lock)
        self.assertEqual(snapshot(self.folder), installed)

    @unittest.skipUnless(os.name == "posix", "replacing a file that is open needs POSIX semantics")
    def test_a_release_reading_the_launcher_goes_on_reading_it(self):
        self.run_install()
        [backup] = self.backups()
        with open(self.folder / "releaseGeneral.sh", "rb") as running, redirect_stdout(io.StringIO()):
            install.restore(self.folder, backup, locker=free_lock)
            self.assertEqual(running.read(), LAUNCHER_BYTES)

    def test_refuses_to_run_as_root(self):
        self.run_install()
        [backup] = self.backups()
        installed = snapshot(self.folder)
        with mock.patch.object(install.os, "geteuid", return_value=0, create=True):
            with self.assertRaises(install.Refused), redirect_stdout(io.StringIO()):
                install.restore(self.folder, backup, locker=free_lock)
        self.assertEqual(snapshot(self.folder), installed)

    @unittest.skipUnless(os.name == "posix", "symlinks need extra rights on Windows")
    def test_refuses_to_restore_over_a_pipeline_that_is_a_symlink(self):
        self.run_install()
        [backup] = self.backups()
        elsewhere = self.tmp / "elsewhere"
        elsewhere.mkdir()
        (self.folder / "pipeline").symlink_to(elsewhere)
        installed = snapshot(self.folder)
        with self.assertRaises(install.Refused) as caught, redirect_stdout(io.StringIO()):
            install.restore(self.folder, backup, locker=free_lock)
        self.assertIn("restore over it", str(caught.exception))
        self.assertEqual(snapshot(self.folder), installed)

    @unittest.skipUnless(os.name == "posix", "file modes are POSIX")
    def test_puts_each_file_back_with_its_mode(self):
        (self.folder / "releaseGeneral.sh").chmod(0o640)
        self.run_install()
        [backup] = self.backups()
        with redirect_stdout(io.StringIO()):
            install.restore(self.folder, backup, locker=free_lock)
        self.assertEqual((self.folder / "releaseGeneral.sh").stat().st_mode & 0o777, 0o640)


class CommandLine(InstallerTest):
    def test_install_options_do_not_apply_to_check_or_restore(self):
        # --check --side production would otherwise check the folder's own side, silently
        for args in (("--check", "--side", "production"), ("--check", "--branch", "x"), ("--restore", "x", "--force")):
            with self.subTest(args=args):
                with self.assertRaises(SystemExit) as caught:
                    self.run_main("--folder", str(self.folder), *args)
                self.assertEqual(caught.exception.code, 2)

    def test_installing_needs_a_side(self):
        with self.assertRaises(SystemExit) as caught:
            self.run_main("--folder", str(self.folder))
        self.assertEqual(caught.exception.code, 2)

    def test_a_refusal_exits_1_with_the_reason(self):
        (self.folder / "ResourcePackScripts").rename(self.tmp / "moved-away")
        code, out, err = self.run_main("--side", "test", "--folder", str(self.folder))
        self.assertEqual(code, 1)
        self.assertIn("isn't an automation folder", err)


@unittest.skipUnless(os.name == "posix" and shutil.which("flock"), "the real release lock needs fcntl and flock")
class RealLock(InstallerTest):
    def test_refuses_with_75_while_the_launcher_lock_is_held(self):
        import signal

        # Held as the launcher holds it: by util-linux flock, in another process
        (self.folder / "runs").mkdir()
        holder = subprocess.Popen(
            ["flock", str(self.folder / "runs" / ".lock"), "sh", "-c", "echo held; sleep 30"],
            stdout=subprocess.PIPE, text=True, start_new_session=True,
        )
        self.addCleanup(holder.stdout.close)
        self.addCleanup(holder.wait)
        # flock's child inherits the lock, so end the whole group, not flock alone
        self.addCleanup(os.killpg, holder.pid, signal.SIGKILL)
        self.assertEqual(holder.stdout.readline(), "held\n")
        before = snapshot(self.folder)
        code, out, err = self.run_main("--side", "test", "--folder", str(self.folder))
        self.assertEqual(code, 75)
        self.assertIn("A release is running", err)
        self.assertEqual(snapshot(self.folder), before)

    def test_takes_the_real_lock_and_lets_it_go(self):
        import fcntl

        code, out, err = self.run_main("--side", "test", "--folder", str(self.folder))
        self.assertEqual(code, 0, err)
        with open(self.folder / "runs" / ".lock", "a") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)  # raises if still held

    @unittest.skipUnless(os.name == "posix" and os.geteuid() != 0, "file modes are POSIX, and root ignores them")
    def test_refuses_a_lock_file_it_cannot_open(self):
        # What a sudo install leaves behind. It used to end in a PermissionError traceback
        (self.folder / "runs").mkdir()
        lock = self.folder / "runs" / ".lock"
        lock.write_text("")
        lock.chmod(0o444)
        self.addCleanup(lock.chmod, 0o644)
        before = snapshot(self.folder)
        code, out, err = self.run_main("--side", "test", "--folder", str(self.folder))
        self.assertEqual(code, 1)
        self.assertIn("runs/.lock can't be opened: Permission denied", err)
        self.assertEqual(snapshot(self.folder), before)


if __name__ == "__main__":
    unittest.main()
