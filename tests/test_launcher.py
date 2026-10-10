"""Tests for automation/launcher.sh, run as MCME-Architect runs it: `sh <name> <args>`.

Linux only - the launcher needs util-linux's flock, as on the server - and
plain unittest, so WSL can run it without pytest. Each test builds a throwaway
automation folder whose ResourcePackScripts checkout is a clone of a local
"origin" repository holding fake release scripts.
"""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LAUNCHER = REPO_ROOT / "automation" / "launcher.sh"
CONF_TOOL = REPO_ROOT / "automation" / "automation_conf.py"

ARGS = ["Rohan", "MCME", "RP-Rohan", "v1.0", "Better leaves"]

# The lock probe prints flock's status: 1 the lock is held, 0 it's free, 66 no runs/.lock here
FAKE_SCRIPT = """\
echo "ran releaseGeneral {version}: $#:$1|$2|$3|$4|$5"
echo "parent $PPID, in $(pwd)"
flock -n runs/.lock true; echo "lock probe: $?"
"""

FAKE_WRAPPER = """\
#!/bin/sh
echo "wrapper (parent $PPID) got: $1"
shift
echo "args: $#:$1|$2|$3|$4|$5"
"""

GIT_ENV = dict(
    os.environ,
    GIT_AUTHOR_NAME="test",
    GIT_AUTHOR_EMAIL="test@example.com",
    GIT_COMMITTER_NAME="test",
    GIT_COMMITTER_EMAIL="test@example.com",
)

TOOLS_PRESENT = os.name == "posix" and all(shutil.which(tool) for tool in ("sh", "git", "flock", "python3"))


def git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, env=GIT_ENV, check=True, capture_output=True)


@unittest.skipUnless(TOOLS_PRESENT, "needs Linux with sh, git, flock and python3, as on the server")
class Launcher(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        self.seed = tmp / "seed"
        self.origin = tmp / "origin.git"
        self.folder = tmp / "resourcePackAutomation"
        self.checkout = self.folder / "ResourcePackScripts"

        git("init", "-q", "-b", "development", str(self.seed), cwd=tmp)
        (self.seed / "automation" / "scripts").mkdir(parents=True)
        (self.seed / "automation" / "pipeline").mkdir()
        shutil.copy(CONF_TOOL, self.seed / "automation" / "automation_conf.py")
        self.write_script("v1")
        wrapper = self.seed / "automation" / "pipeline" / "run"
        wrapper.write_text(FAKE_WRAPPER)
        wrapper.chmod(0o755)
        git("add", "-A", cwd=self.seed)
        git("commit", "-q", "-m", "seed", cwd=self.seed)
        git("clone", "-q", "--bare", str(self.seed), str(self.origin), cwd=tmp)

        self.folder.mkdir()
        git("clone", "-q", "-b", "development", str(self.origin), str(self.checkout), cwd=tmp)
        self.write_conf(wrapper="no")
        self.install("releaseGeneral.sh")

    def write_script(self, version):
        script = self.seed / "automation" / "scripts" / "releaseGeneral.sh"
        script.write_text(FAKE_SCRIPT.format(version=version))

    def push(self, message):
        git("commit", "-q", "-am", message, cwd=self.seed)
        git("push", "-q", str(self.origin), "development", cwd=self.seed)

    def write_conf(self, **overrides):
        settings = {"side": "test", "branch": "development", "replace_existing": "yes", "wrapper": "yes", **overrides}
        (self.folder / "automation.conf").write_text("".join(f"{k}={v}\n" for k, v in settings.items()))

    def install(self, name):
        shutil.copy(LAUNCHER, self.folder / name)

    def launch(self, name="releaseGeneral.sh", args=ARGS, env=GIT_ENV):
        # Started from another folder: the launcher must find its own. The timeout
        # turns a launcher that waits for the lock into an error instead of a hang
        return subprocess.run(
            ["sh", str(self.folder / name), *args],
            cwd=self.folder.parent, capture_output=True, text=True, env=env, timeout=30,
        )

    def test_runs_the_script_with_the_original_arguments(self):
        result = self.launch()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ran releaseGeneral v1: 5:Rohan|MCME|RP-Rohan|v1.0|Better leaves", result.stdout)

    def test_passes_awkward_arguments_intact(self):
        args = ["Human", "", "*", "$HOME `id` $(id)", "it's \"quoted\""]
        result = self.launch(args=args)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ran releaseGeneral v1: 5:Human||*|$HOME `id` $(id)|it's \"quoted\"", result.stdout)

    def test_runs_the_script_in_the_automation_folder(self):
        self.assertIn(f", in {self.folder}\n", self.launch().stdout)

    def test_hands_over_with_exec(self):
        # With exec the script is the process this test started, so its parent is this test
        self.assertIn(f"parent {os.getpid()},", self.launch().stdout)

    def test_holds_the_lock_while_the_script_runs(self):
        self.assertIn("lock probe: 1", self.launch().stdout)

    def test_git_fetch_and_merge_run_without_the_lock(self):
        # A detached `git maintenance` they leave behind would hold the lock after the release.
        # The fake git logs to a file: the launcher keeps the fetch's stderr to itself
        bin_dir = self.folder.parent / "bin"
        bin_dir.mkdir()
        calls = self.folder.parent / "git-calls"
        fake_git = bin_dir / "git"
        fake_git.write_text(
            "#!/bin/sh\n"
            "if [ -e /proc/self/fd/9 ]; then fd9=open; else fd9=closed; fi\n"
            f'echo "fd 9 $fd9, prompt ${{GIT_TERMINAL_PROMPT:-unset}}: git $*" >> "{calls}"\n'
            f'exec {shutil.which("git")} "$@"\n'
        )
        fake_git.chmod(0o755)
        self.write_script("v2")
        self.push("v2")
        result = self.launch(env=dict(GIT_ENV, PATH=f"{bin_dir}:{os.environ['PATH']}"))
        self.assertIn("ran releaseGeneral v2:", result.stdout)
        logged = calls.read_text().splitlines()
        for command, wanted in ((" fetch ", "fd 9 closed, prompt 0:"), (" merge ", "fd 9 closed,")):
            with self.subTest(command=command.strip()):
                seen = [line for line in logged if command in line]
                self.assertTrue(seen, f"the fake git never saw a{command}")
                self.assertEqual([line for line in seen if not line.startswith(wanted)], [])

    def test_brings_the_checkout_up_to_date_before_running_the_script(self):
        self.write_script("v2")
        self.push("v2")
        self.assertIn("ran releaseGeneral v2:", self.launch().stdout)

    def test_says_which_commit_it_releases_with(self):
        self.write_script("v2")
        self.push("v2")
        head = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=self.seed, capture_output=True, text=True, check=True
        ).stdout.strip()
        result = self.launch()
        self.assertIn(f"Releasing with ResourcePackScripts development at {head}.", result.stderr)

    def test_follows_the_branch_when_github_has_a_tag_of_the_same_name(self):
        # "git fetch origin development" would fetch the tag, and the folder would stop following the branch
        git("tag", "development", "refs/heads/development", cwd=self.origin)
        self.write_script("v2")
        self.push("v2")
        result = self.launch()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ran releaseGeneral v2:", result.stdout)

    def test_refuses_a_history_rewritten_on_github(self):
        # Without the + in the refspec the fetch is refused, and the release quietly runs the old scripts
        self.write_script("v2")
        git("commit", "-q", "--amend", "-am", "rewritten", cwd=self.seed)
        git("push", "-q", "-f", str(self.origin), "development", cwd=self.seed)
        result = self.launch()
        self.assertEqual(result.returncode, 3)
        self.assertIn("GitHub's history was rewritten", result.stderr)
        self.assertNotIn("ran releaseGeneral", result.stdout)

    def test_records_the_running_release(self):
        self.launch()
        current = (self.folder / "runs" / "current").read_text()
        self.assertIn("releaseGeneral.sh Rohan MCME RP-Rohan v1.0 Better leaves", current)

    def test_refuses_while_another_release_holds_the_lock(self):
        import fcntl

        (self.folder / "runs").mkdir()
        (self.folder / "runs" / "current").write_text(
            "releaseVanillaSodium.sh Human MCME RP-Human v4.1.3 Leaves (started 2026-10-10 12:00:00)\n"
        )
        handle = open(self.folder / "runs" / ".lock", "a")
        self.addCleanup(handle.close)
        fcntl.flock(handle, fcntl.LOCK_EX)
        result = self.launch()
        self.assertEqual(result.returncode, 75)
        self.assertIn("Another release is running: releaseVanillaSodium.sh Human", result.stderr)
        self.assertNotIn("ran releaseGeneral", result.stdout)

    def test_a_broken_flock_is_not_reported_as_a_running_release(self):
        # flock -n exits 1 when the lock is held; any other status means flock itself failed
        bin_dir = self.folder.parent / "bin"
        bin_dir.mkdir()
        fake_flock = bin_dir / "flock"
        fake_flock.write_text('#!/bin/sh\necho "flock: broken" >&2\nexit 64\n')
        fake_flock.chmod(0o755)
        result = self.launch(env=dict(GIT_ENV, PATH=f"{bin_dir}:{os.environ['PATH']}"))
        self.assertEqual(result.returncode, 2)
        self.assertIn("Couldn't take the release lock", result.stderr)
        self.assertNotIn("Another release is running", result.stderr)
        self.assertNotIn("ran releaseGeneral", result.stdout)

    def test_refuses_a_folder_without_automation_conf(self):
        (self.folder / "automation.conf").unlink()
        result = self.launch()
        self.assertEqual(result.returncode, 2)
        self.assertIn("isn't installed", result.stderr)
        self.assertNotIn("ran releaseGeneral", result.stdout)

    def test_refuses_an_invalid_automation_conf(self):
        self.write_conf(side="staging")
        result = self.launch()
        self.assertEqual(result.returncode, 2)
        self.assertIn("staging", result.stderr)

    def test_refuses_a_checkout_edited_on_the_server(self):
        script = self.checkout / "automation" / "scripts" / "releaseGeneral.sh"
        script.write_text(script.read_text() + "echo edited on the server\n")
        result = self.launch()
        self.assertEqual(result.returncode, 3)
        self.assertIn("edited ResourcePackScripts on the server", result.stderr)

    def test_refuses_a_checkout_on_another_branch(self):
        git("checkout", "-q", "-b", "hotfix", cwd=self.checkout)
        result = self.launch()
        self.assertEqual(result.returncode, 3)
        self.assertIn("on 'hotfix'", result.stderr)

    def test_refuses_a_checkout_that_has_diverged_from_github(self):
        (self.checkout / "local.txt").write_text("a commit made on the server\n")
        git("add", "local.txt", cwd=self.checkout)
        git("commit", "-q", "-m", "server-side commit", cwd=self.checkout)
        self.write_script("v2")
        self.push("v2")
        result = self.launch()
        self.assertEqual(result.returncode, 3)
        self.assertIn("commits that GitHub's development doesn't", result.stderr)

    def test_refuses_a_commit_made_on_the_server(self):
        # GitHub hasn't moved, so merge --ff-only alone would call this "already up to date"
        (self.checkout / "local.txt").write_text("a commit made on the server\n")
        git("add", "local.txt", cwd=self.checkout)
        git("commit", "-q", "-m", "server-side commit", cwd=self.checkout)
        result = self.launch()
        self.assertEqual(result.returncode, 3)
        self.assertIn("commits that GitHub's development doesn't", result.stderr)
        self.assertNotIn("ran releaseGeneral", result.stdout)

    def test_refuses_a_branch_github_does_not_have(self):
        git("checkout", "-q", "-b", "hotfix", cwd=self.checkout)
        self.write_conf(wrapper="no", branch="hotfix")
        result = self.launch()
        self.assertEqual(result.returncode, 3)
        self.assertIn("GitHub has no branch 'hotfix'", result.stderr)
        self.assertNotIn("ran releaseGeneral", result.stdout)

    def test_refuses_a_detached_checkout(self):
        git("checkout", "-q", "--detach", cwd=self.checkout)
        result = self.launch()
        self.assertEqual(result.returncode, 3)
        self.assertIn("on 'no branch'", result.stderr)

    def test_carries_on_when_github_cannot_be_reached(self):
        git("remote", "set-url", "origin", str(self.folder.parent / "gone.git"), cwd=self.checkout)
        result = self.launch()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Couldn't fetch 'development' from GitHub", result.stderr)
        self.assertIn("ran releaseGeneral v1:", result.stdout)

    def test_hands_over_to_the_wrapper_when_asked(self):
        self.write_conf(wrapper="yes")
        result = self.launch()
        self.assertEqual(result.returncode, 0, result.stderr)
        script = self.checkout / "automation" / "scripts" / "releaseGeneral.sh"
        self.assertIn(f"wrapper (parent {os.getpid()}) got: {script}", result.stdout)
        self.assertIn("args: 5:Rohan|MCME|RP-Rohan|v1.0|Better leaves", result.stdout)

    def test_refuses_the_wrapper_when_the_checkout_has_none(self):
        self.write_conf(wrapper="yes")
        (self.seed / "automation" / "pipeline" / "run").unlink()
        self.push("no wrapper")
        result = self.launch()
        self.assertEqual(result.returncode, 2)
        self.assertIn("no automation/pipeline/run", result.stderr)

    def test_refuses_a_wrapper_that_is_not_executable(self):
        # Committed without +x it isn't a missing wrapper, and exec alone would only say "Permission denied"
        self.write_conf(wrapper="yes")
        (self.seed / "automation" / "pipeline" / "run").chmod(0o644)
        self.push("wrapper without +x")
        result = self.launch()
        self.assertEqual(result.returncode, 2)
        self.assertIn("isn't executable", result.stderr)
        self.assertIn("100755", result.stderr)

    def test_refuses_a_name_with_no_script(self):
        self.install("releaseUnknown.sh")
        result = self.launch("releaseUnknown.sh")
        self.assertEqual(result.returncode, 2)
        self.assertIn("no release script called releaseUnknown.sh", result.stderr)
        self.assertNotIn("Releasing with", result.stderr)


if __name__ == "__main__":
    unittest.main()
