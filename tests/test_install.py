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
        self.folder = self.tmp / "resourcePackAutomation"
        checkout = self.folder / "ResourcePackScripts"
        checkout.mkdir(parents=True)
        git("init", "-q", "-b", "development", cwd=checkout)
        git("remote", "add", "origin", "https://github.com/MCME/ResourcePackScripts.git", cwd=checkout)
        (checkout / "README.md").write_text("checkout\n")
        # What the launchers hand over to, which --check looks for
        (checkout / "automation" / "scripts").mkdir(parents=True)
        for name in install.SCRIPT_NAMES:
            (checkout / "automation" / "scripts" / name).write_text("# a release script\n")
        (checkout / "automation" / "pipeline").mkdir()
        (checkout / "automation" / "pipeline" / "run").write_text("#!/bin/sh\n")
        (checkout / "automation" / "pipeline" / "run").chmod(0o755)
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
        ):
            with self.subTest(url=url):
                git("remote", "set-url", "origin", url, cwd=self.folder / "ResourcePackScripts")
                self.assertEqual(install.check_folder(self.folder), ["Human-Sodium", "Rohan-Vanilla"])

    def test_refuses_other_repositories(self):
        for url in (
            "https://github.com/someone/ResourcePackScripts.git",
            "https://github.com/MCME/ResourcePackScripts-fork.git",
            "https://notgithub.com/MCME/ResourcePackScripts.git",
        ):
            with self.subTest(url=url):
                git("remote", "set-url", "origin", url, cwd=self.folder / "ResourcePackScripts")
                with self.assertRaises(install.Refused):
                    install.check_folder(self.folder)

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


if __name__ == "__main__":
    unittest.main()
