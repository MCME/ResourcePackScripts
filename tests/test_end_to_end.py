"""End to end, on Linux: install an automation folder, check it, release
through the installed launcher and the wrapper, refuse a second release while
one holds the lock, and undo the install with the command install.py printed.

The launcher, installer, wrapper and release scripts are the real ones, in a
checkout of a local copy of this repository that the launcher fetches as it
would fetch GitHub. Only 7-Zip, gh and generateVanilla are stand-ins
(tests/release_helpers.py). Plain unittest, so WSL can run it without pytest.
"""

import json
import os
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

import release_helpers  # noqa: E402

GITHUB = "https://github.com/MCME/ResourcePackScripts.git"
RELEASE = ["Rohan", "MCME", "RP-Rohan", "v1.0", "Better leaves"]
TOOLS_PRESENT = (
    os.name == "posix" and os.geteuid() != 0
    and all(shutil.which(tool) for tool in ("sh", "git", "flock", "python3"))
)

# git as on the server, with nothing from the developer's own config. And no
# PYTHONDONTWRITEBYTECODE: install.py's import leaves __pycache__/ in the
# checkout, as it does there, and the launcher must still find it clean
ENV = {key: value for key, value in os.environ.items() if not key.startswith(("RP_", "FAKE_", "GIT_"))}
ENV.pop("PYTHONDONTWRITEBYTECODE", None)
ENV.update(
    GIT_AUTHOR_NAME="test", GIT_AUTHOR_EMAIL="test@example.com",
    GIT_COMMITTER_NAME="test", GIT_COMMITTER_EMAIL="test@example.com",
    GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1",
)


def git(*args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, env=ENV, check=True, capture_output=True, text=True).stdout.strip()


def stop(process):
    """End a process started in its own session, with everything it started."""
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


@unittest.skipUnless(TOOLS_PRESENT, "needs Linux with sh, git, flock and python3, as on the server, and not root")
class EndToEnd(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        github = self.tmp / "github"

        # "GitHub's" ResourcePackScripts: this repository's automation/, with a stand-in generateVanilla
        seed = self.tmp / "seed"
        shutil.copytree(REPO_ROOT / "automation", seed / "automation", ignore=shutil.ignore_patterns("__pycache__"))
        (seed / "generateVanilla").mkdir()
        shutil.copy(REPO_ROOT / "generateVanilla" / "pack_formats.json", seed / "generateVanilla")
        (seed / "generateVanilla" / "generateVanilla.py").write_text(release_helpers.FAKE_GENERATE)
        (seed / "generateVanilla" / "objmc.py").write_text("")
        shutil.copy(REPO_ROOT / ".gitignore", seed / ".gitignore")
        git("init", "-q", "-b", "development", str(seed), cwd=self.tmp)
        git("add", "-A", cwd=seed)
        git("commit", "-q", "-m", "ResourcePackScripts", cwd=seed)
        scripts_origin = github / "ResourcePackScripts.git"
        git("clone", "-q", "--bare", str(seed), str(scripts_origin), cwd=self.tmp)

        # The pack's repository
        pack_seed = self.tmp / "pack-seed"
        textures = pack_seed / "assets" / "minecraft" / "textures" / "block"
        textures.mkdir(parents=True)
        mcmeta = {"pack": {"min_format": 88, "max_format": 97, "description": "Rohan"}}
        (pack_seed / "pack.mcmeta").write_text(json.dumps(mcmeta))
        (textures / "activator_rail.png").write_bytes(b"pack rail")
        (pack_seed / "inventories").mkdir()
        (pack_seed / "inventories" / "blocks.json").write_text("{}")
        git("init", "-q", "-b", "development", str(pack_seed), cwd=self.tmp)
        git("add", "-A", cwd=pack_seed)
        git("commit", "-q", "-m", "Rohan", cwd=pack_seed)
        pack_origin = github / "RP-Rohan.git"
        git("clone", "-q", "--bare", str(pack_seed), str(pack_origin), cwd=self.tmp)

        # The test automation folder as it is before the install, inside the RP server's folder
        self.folder = self.tmp / "network" / "rpserver" / "resourcePackAutomation"
        self.folder.mkdir(parents=True)
        checkout = self.folder / "ResourcePackScripts"
        git("clone", "-q", "-b", "development", str(scripts_origin), str(checkout), cwd=self.tmp)
        git("remote", "set-url", "origin", GITHUB, cwd=checkout)
        git("clone", "-q", "-b", "development", str(pack_origin), str(self.folder / "Rohan-Vanilla"), cwd=self.tmp)
        (self.folder / "Footprints").mkdir()
        (self.folder / "Footprints" / "activator_rail.png").write_bytes(b"footprints rail")
        (self.folder / "Footprints" / "activator_rail_on.png").write_bytes(b"footprints rail, powered")
        (self.folder / "releaseGeneral.sh").write_text("# the hand-edited copy\n")
        (self.folder / "pipeline").mkdir()
        (self.folder / "pipeline" / "run.sh").write_text("# the old wrapper\n")

        release_helpers.install_fakes(self.tmp / "bin", ("7z", "gh"))
        self.log = self.tmp / "calls.jsonl"
        tools = dict(
            ENV, PATH=f"{self.tmp / 'bin'}:{os.environ['PATH']}",
            FAKE_LOG=str(self.log), FAKE_GH_RELEASES=str(self.tmp / "releases.txt"),
        )
        # install.py reads origin's URL as written; the launcher's fetches of it go to the local "GitHub"
        self.as_admin = tools
        redirect = self.tmp / "gitconfig"
        redirect.write_text(f'[url "{scripts_origin}"]\n\tinsteadOf = {GITHUB}\n')
        self.as_architect = dict(tools, GIT_CONFIG_GLOBAL=str(redirect))

    def run_in_folder(self, *command, env):
        return subprocess.run(list(command), cwd=self.folder, capture_output=True, text=True, env=env, timeout=120)

    def test_install_check_release_refuse_and_undo(self):
        installer = "ResourcePackScripts/automation/install.py"

        # 1. Install, as the runbook does
        result = self.run_in_folder("python3", installer, "--side", "test", env=self.as_admin)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        [backed_up] = [line for line in result.stdout.splitlines() if line.startswith("Backed up into ")]
        undo = shlex.split(backed_up.split("Undo with: ", 1)[1])

        # 2. Ready
        result = self.run_in_folder("python3", installer, "--check", env=self.as_admin)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("Ready.", result.stdout)

        # 3. A release, as MCME-Architect starts one: sh <script> <args>, in the folder
        result = self.run_in_folder("sh", "releaseGeneral.sh", *RELEASE, env=self.as_architect)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Releasing with ResourcePackScripts development at", result.stderr)
        [summary_path] = (self.folder / "runs").glob("*-Rohan-v1.0.json")
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        commit = git("rev-parse", "HEAD", cwd=self.folder / "ResourcePackScripts")
        self.assertEqual(summary["automation"], {"side": "test", "branch": "development", "commit": commit})
        self.assertEqual((summary["status"], summary["outcome"]), ("ok", "published"), summary["problems"])
        self.assertIn(f"Release run {summary['id']}: OK, released.", result.stdout)
        [create] = [call["args"] for call in release_helpers.calls(self.log, "gh") if call["args"][1] == "create"]
        self.assertIn("--notes=Version v1.0 for Minecraft 26.2 and 26.3", create)
        self.assertFalse((self.folder / "runs" / "current").exists())

        # 4. A second release while another holds the lock: refused through the wrapper, which notes it.
        #    -w 10: a lock step 3 left held fails the test instead of hanging it
        holder = subprocess.Popen(
            ["flock", "-w", "10", str(self.folder / "runs" / ".lock"), "sh", "-c", "echo held; sleep 60"],
            stdout=subprocess.PIPE, text=True, start_new_session=True,
        )
        self.addCleanup(holder.stdout.close)
        self.addCleanup(stop, holder)
        self.assertEqual(holder.stdout.readline(), "held\n")
        later = ["Rohan", "MCME", "RP-Rohan", "v1.1", "Later"]
        result = self.run_in_folder("sh", "releaseGeneral.sh", *later, env=self.as_architect)
        self.assertEqual(result.returncode, 75)
        refused = (self.folder / "runs" / "refused.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(json.loads(refused[-1])["tag"], "v1.1")
        stop(holder)
        # The holder's sh and sleep may outlive flock for a moment, and hold the lock until they end
        release_helpers.wait_until_free(self.folder / "runs" / ".lock")

        # 5. Undo with the command install.py printed
        result = self.run_in_folder(*undo, env=self.as_admin)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.folder / "releaseGeneral.sh").read_text(), "# the hand-edited copy\n")
        self.assertEqual((self.folder / "pipeline" / "run.sh").read_text(), "# the old wrapper\n")
        self.assertFalse((self.folder / "automation.conf").exists())
        self.assertFalse((self.folder / "releaseVanillaSodium.sh").exists())


if __name__ == "__main__":
    unittest.main()
