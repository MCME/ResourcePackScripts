"""Tests for automation/launcher.sh, run as MCME-Architect runs it: `sh <name> <args>`.

Linux only - the launcher needs util-linux's flock, as on the server - and
plain unittest, so WSL can run it without pytest. Each test builds a throwaway
automation folder whose ResourcePackScripts checkout is a clone of a local
"origin" repository holding fake release scripts, a fake wrapper and the real
settings reader.
"""

import os
import shutil
import signal
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LAUNCHER = REPO_ROOT / "automation" / "launcher.sh"
CONF_TOOL = REPO_ROOT / "automation" / "automation_conf.py"
sys.path.insert(0, str(Path(__file__).resolve().parent))

import release_helpers  # noqa: E402

ARGS = ["Rohan", "MCME", "RP-Rohan", "v1.0", "Better leaves"]

# The lock probe prints flock's status: 1 the lock is held, 0 it's free, 66 no runs/.lock here
FAKE_SCRIPT = """\
echo "ran releaseGeneral {version}: $#:$1|$2|$3|$4|$5"
echo "parent $PPID, in $(pwd)"
flock -n runs/.lock true; echo "lock probe: $?"
echo "settings: $RP_AUTOMATION_SIDE $RP_AUTOMATION_BRANCH $RP_AUTOMATION_REPLACE_EXISTING $RP_AUTOMATION_COMMIT"
"""

# A release that takes its time, for the test that stops one as Architect does
SLOW_SCRIPT = """\
echo started
sleep 30
"""

# The wrapper's own check that it runs under the launcher's lock: descriptor 9 is
# runs/.lock, and flock on that same open file succeeds while a fresh open would not
FAKE_WRAPPER = """\
echo "wrapper (parent $PPID) got: $1"
if [ /proc/self/fd/9 -ef runs/.lock ] && flock -n 9; then echo "wrapper holds the lock"; fi
shift
echo "args: $#:$1|$2|$3|$4|$5"
"""

# The wrapper's rp-release.py, as far as the launcher uses it: refusing a release
FAKE_RP_RELEASE = """\
import os
import sys

print("rp-release.py " + " ".join(sys.argv[1:]))
sys.exit(int(os.environ.get("FAKE_RP_RELEASE_EXIT", "0")))
"""

GIT_ENV = dict(
    os.environ,
    GIT_AUTHOR_NAME="test",
    GIT_AUTHOR_EMAIL="test@example.com",
    GIT_COMMITTER_NAME="test",
    GIT_COMMITTER_EMAIL="test@example.com",
    # The developer's own git config never reaches these tests
    GIT_CONFIG_GLOBAL=os.devnull,
    GIT_CONFIG_NOSYSTEM="1",
)

TOOLS_PRESENT = os.name == "posix" and all(shutil.which(tool) for tool in ("sh", "git", "flock", "python3"))


def git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, env=GIT_ENV, check=True, capture_output=True)


def git_output(*args, cwd):
    result = subprocess.run(["git", *args], cwd=cwd, env=GIT_ENV, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def stop(process):
    """End a process started in its own session, with everything it started, as Architect does."""
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


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
        # Committed without the executable bit: the launcher runs the wrapper with sh (P1)
        (self.seed / "automation" / "pipeline" / "run.sh").write_text(FAKE_WRAPPER)
        (self.seed / "automation" / "pipeline" / "rp-release.py").write_text(FAKE_RP_RELEASE)
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
        git("add", "-A", cwd=self.seed)
        git("commit", "-q", "-m", message, cwd=self.seed)
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

    def hold_the_lock(self):
        """Hold runs/.lock as a running release does, until the test ends."""
        import fcntl

        (self.folder / "runs").mkdir(exist_ok=True)
        handle = open(self.folder / "runs" / ".lock", "a")
        self.addCleanup(handle.close)
        fcntl.flock(handle, fcntl.LOCK_EX)

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

    def test_every_git_command_runs_without_the_lock(self):
        # A detached `git maintenance` left behind would hold the lock after the release.
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
        for command in (" symbolic-ref ", " status ", " fetch ", " merge-base ", " merge ", " rev-parse "):
            with self.subTest(command=command.strip()):
                self.assertTrue([line for line in logged if command in line], f"the fake git never saw a{command}")
        self.assertEqual([line for line in logged if not line.startswith("fd 9 closed")], [])
        self.assertEqual([line for line in logged if " fetch " in line and "prompt 0:" not in line], [])

    def test_brings_the_checkout_up_to_date_before_running_the_script(self):
        self.write_script("v2")
        self.push("v2")
        self.assertIn("ran releaseGeneral v2:", self.launch().stdout)

    def test_says_which_commit_it_releases_with(self):
        self.write_script("v2")
        self.push("v2")
        head = git_output("rev-parse", "--short", "HEAD", cwd=self.seed)
        result = self.launch()
        self.assertIn(f"Releasing with ResourcePackScripts development at {head}.", result.stderr)

    def test_tells_the_release_what_it_runs_with(self):
        # The scripts' setting, and the side, branch and commit for the wrapper's run summary
        commit = git_output("rev-parse", "HEAD", cwd=self.seed)
        self.assertIn(f"settings: test development yes {commit}\n", self.launch().stdout)

    def test_tells_the_release_it_runs_on_production(self):
        # A production folder's settings, as the scripts read them. The branch stays development:
        # the test checkout is on it
        self.write_conf(side="production", branch="development", replace_existing="no", wrapper="no")
        commit = git_output("rev-parse", "HEAD", cwd=self.seed)
        self.assertIn(f"settings: production development no {commit}\n", self.launch().stdout)

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

    def test_clears_its_record_when_it_stops_before_the_hand_over(self):
        # Otherwise a release refused later would name this one as running
        script = self.checkout / "automation" / "scripts" / "releaseGeneral.sh"
        script.write_text(script.read_text() + "echo edited on the server\n")
        self.assertEqual(self.launch().returncode, 3)
        self.assertFalse((self.folder / "runs" / "current").exists())

    def test_refuses_while_another_release_holds_the_lock(self):
        (self.folder / "runs").mkdir()
        (self.folder / "runs" / "current").write_text(
            "releaseVanillaSodium.sh Human MCME RP-Human v4.1.3 Leaves (started 2026-10-10 12:00:00)\n"
        )
        self.hold_the_lock()
        result = self.launch()
        self.assertEqual(result.returncode, 75)
        self.assertIn("Another release is running: releaseVanillaSodium.sh Human", result.stderr)
        self.assertNotIn("ran releaseGeneral", result.stdout)
        # The record is the running release's: a refusal leaves it alone
        self.assertIn("RP-Human", (self.folder / "runs" / "current").read_text())

    def test_a_refusal_goes_through_the_wrapper_when_the_folder_uses_it(self):
        # P2: the wrapper says which release runs, and notes the attempt for the dashboard
        self.write_conf(wrapper="yes")
        self.hold_the_lock()
        result = self.launch()
        self.assertEqual(result.returncode, 75)
        self.assertIn(
            "rp-release.py refused --runs runs --script releaseGeneral.sh --server-log ../logs/latest.log"
            " -- Rohan MCME RP-Rohan v1.0 Better leaves",
            result.stdout,
        )
        self.assertNotIn("Another release is running", result.stderr)

    def test_a_refusal_says_it_itself_when_the_wrapper_cannot(self):
        self.write_conf(wrapper="yes")
        self.hold_the_lock()
        result = self.launch(env=dict(GIT_ENV, FAKE_RP_RELEASE_EXIT="1"))
        self.assertEqual(result.returncode, 75)
        self.assertIn("Another release is running", result.stderr)

    def test_the_lock_comes_free_when_architect_stops_a_release(self):
        # At its timeout Architect stops the release and everything it started (TERM, then KILL)
        (self.seed / "automation" / "scripts" / "releaseSlow.sh").write_text(SLOW_SCRIPT)
        self.push("a slow release")
        self.install("releaseSlow.sh")
        slow = subprocess.Popen(
            ["sh", str(self.folder / "releaseSlow.sh"), *ARGS], cwd=self.folder, env=GIT_ENV,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, start_new_session=True,
        )
        self.addCleanup(slow.stdout.close)
        self.addCleanup(stop, slow)
        self.assertEqual(slow.stdout.readline(), "started\n")
        self.assertEqual(self.launch().returncode, 75)
        os.killpg(slow.pid, signal.SIGTERM)
        slow.wait(timeout=10)
        # The script's `sleep` may outlive it for a moment, and holds the lock until it ends
        release_helpers.wait_until_free(self.folder / "runs" / ".lock")
        result = self.launch()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ran releaseGeneral v1:", result.stdout)

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
        self.assertFalse((self.folder / "runs").exists())

    def test_refuses_a_folder_without_a_checkout(self):
        shutil.rmtree(self.checkout)
        result = self.launch()
        self.assertEqual(result.returncode, 2)
        self.assertIn("isn't installed", result.stderr)
        self.assertFalse((self.folder / "runs").exists())

    def test_refuses_an_invalid_automation_conf(self):
        self.write_conf(side="staging")
        result = self.launch()
        self.assertEqual(result.returncode, 2)
        self.assertIn("staging", result.stderr)
        self.assertIn("automation.conf is invalid", result.stderr)
        self.assertNotIn("ran releaseGeneral", result.stdout)

    def test_a_settings_reader_fixed_on_github_heals_the_folder(self):
        # P3: the launcher updates the checkout before it reads automation.conf
        reader = self.seed / "automation" / "automation_conf.py"
        reader.write_text("this is not Python\n")
        self.push("break the reader")
        git("pull", "-q", "--ff-only", cwd=self.checkout)
        shutil.copy(CONF_TOOL, reader)
        self.push("fix the reader")
        result = self.launch()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ran releaseGeneral v1:", result.stdout)

    def test_says_so_when_the_settings_reader_is_broken_on_github_too(self):
        (self.seed / "automation" / "automation_conf.py").write_text("this is not Python\n")
        self.push("break the reader")
        result = self.launch()
        self.assertEqual(result.returncode, 2)
        self.assertIn("automation_conf.py failed (see above), as it is on GitHub's development", result.stderr)
        self.assertNotIn("isn't installed", result.stderr)
        self.assertNotIn("ran releaseGeneral", result.stdout)

    def test_refuses_a_checkout_edited_on_the_server(self):
        script = self.checkout / "automation" / "scripts" / "releaseGeneral.sh"
        script.write_text(script.read_text() + "echo edited on the server\n")
        result = self.launch()
        self.assertEqual(result.returncode, 3)
        self.assertIn("edited ResourcePackScripts on the server", result.stderr)

    def test_refuses_a_file_added_to_the_checkout_on_the_server(self):
        # An unreviewed script dropped into the checkout must not run, whatever the server's git config says
        git("config", "status.showUntrackedFiles", "no", cwd=self.checkout)
        (self.checkout / "automation" / "scripts" / "releaseExtra.sh").write_text("echo unreviewed\n")
        result = self.launch()
        self.assertEqual(result.returncode, 3)
        self.assertIn("edited ResourcePackScripts on the server", result.stderr)

    def test_refuses_when_git_status_fails(self):
        # Read as "nothing edited", a broken index would let the release go on
        (self.checkout / ".git" / "index").write_bytes(b"not an index")
        result = self.launch()
        self.assertEqual(result.returncode, 3)
        self.assertIn("git status failed", result.stderr)
        self.assertNotIn("ran releaseGeneral", result.stdout)

    def test_refuses_a_checkout_on_another_branch(self):
        git("checkout", "-q", "-b", "hotfix", cwd=self.checkout)
        result = self.launch()
        self.assertEqual(result.returncode, 3)
        self.assertIn("on 'hotfix'", result.stderr)
        self.assertIn("git -C ResourcePackScripts switch development", result.stderr)

    def test_refuses_when_automation_conf_names_another_branch(self):
        # Read after the update: the checkout follows development, the folder says main
        self.write_conf(wrapper="no", branch="main")
        result = self.launch()
        self.assertEqual(result.returncode, 3)
        self.assertIn("ResourcePackScripts is on 'development', but automation.conf says 'main'", result.stderr)
        self.assertIn("git -C ResourcePackScripts switch main", result.stderr)
        self.assertNotIn("ran releaseGeneral", result.stdout)

    def test_says_when_git_cannot_read_the_checkout(self):
        # Not a detached checkout: git itself fails, and says why
        (self.checkout / ".git" / "HEAD").write_text("not a ref\n")
        result = self.launch()
        self.assertEqual(result.returncode, 3)
        self.assertIn("git can't read ResourcePackScripts", result.stderr)
        self.assertNotIn("no branch", result.stderr)

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
        self.assertIn("git -C ResourcePackScripts switch development", result.stderr)

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
        self.assertIn("wrapper holds the lock", result.stdout)

    def test_runs_the_wrapper_with_sh_so_it_needs_no_executable_bit(self):
        # P1: committed as 100644, as Architect's scripts are
        mode = git_output("ls-files", "-s", "automation/pipeline/run.sh", cwd=self.checkout).split()[0]
        self.assertEqual(mode, "100644")
        self.write_conf(wrapper="yes")
        result = self.launch()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("wrapper holds the lock", result.stdout)

    def test_refuses_the_wrapper_when_the_checkout_has_none(self):
        self.write_conf(wrapper="yes")
        (self.seed / "automation" / "pipeline" / "run.sh").unlink()
        self.push("no wrapper")
        result = self.launch()
        self.assertEqual(result.returncode, 2)
        self.assertIn("no automation/pipeline/run.sh", result.stderr)

    def test_refuses_a_name_with_no_script(self):
        self.install("releaseUnknown.sh")
        result = self.launch("releaseUnknown.sh")
        self.assertEqual(result.returncode, 2)
        self.assertIn("no release script called releaseUnknown.sh", result.stderr)
        self.assertNotIn("Releasing with", result.stderr)


class CheckoutHygiene(unittest.TestCase):
    def test_python_caches_stay_out_of_the_checkout(self):
        # install.py and every release import Python from the checkout. An unignored
        # __pycache__/ would make it look edited, and the launcher would refuse every release after
        lines = [line.strip() for line in (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()]
        self.assertIn("__pycache__/", lines)

    def test_shell_files_are_checked_out_with_lf(self):
        # dash stops at a carriage return; .gitattributes keeps *.sh LF even in a Windows checkout
        rules = [line.split() for line in (REPO_ROOT / ".gitattributes").read_text(encoding="utf-8").splitlines()]
        self.assertIn(["*.sh", "text", "eol=lf"], rules)
        scripts = sorted((REPO_ROOT / "automation").rglob("*.sh"))
        self.assertTrue(scripts)
        for script in scripts:
            with self.subTest(script=script.relative_to(REPO_ROOT).as_posix()):
                self.assertNotIn(b"\r", script.read_bytes())


if __name__ == "__main__":
    unittest.main()
