"""Tests for the pipeline wrapper in automation/pipeline/: run.sh and rp-release.py.

rp-release.py's records are tested everywhere. run.sh needs Linux with flock,
as on the server, and is skipped elsewhere. Plain unittest, so WSL can run it
without pytest.
"""

import datetime
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
RUN_SH = REPO_ROOT / "automation" / "pipeline" / "run.sh"
RP_RELEASE = REPO_ROOT / "automation" / "pipeline" / "rp-release.py"
sys.path.insert(0, str(Path(__file__).resolve().parent))

import release_helpers  # noqa: E402

rp_release = release_helpers.load_rp_release()

ARGS = ["Rohan", "MCME", "RP-Rohan", "v1.0", "Better leaves"]
COMMIT = "0123456789abcdef0123456789abcdef01234567"
LAUNCHED = {"RP_AUTOMATION_SIDE": "test", "RP_AUTOMATION_BRANCH": "development", "RP_AUTOMATION_COMMIT": COMMIT}
RECORDED = {"side": "test", "branch": "development", "commit": COMMIT}
TOOLS_PRESENT = os.name == "posix" and all(shutil.which(tool) for tool in ("sh", "flock", "python3"))

# How the launcher starts the wrapper: from the automation folder, holding the lock on descriptor 9
UNDER_THE_LOCK = 'exec 9>>runs/.lock || exit 90; flock -n 9 || exit 91; exec sh "$@"'

# A release script, as far as the wrapper cares: a step line, then what it sees
FAKE_RELEASE = """\
echo "compiling $1 RP zips"
echo "run $RP_RELEASE_RUN"
flock -n runs/.lock true; echo "lock probe: $?"
if [ -e /proc/self/fd/9 ]; then echo "descriptor 9: open"; else echo "descriptor 9: closed"; fi
exit "${FAKE_EXIT:-0}"
"""


def without_launcher_variables():
    return {key: value for key, value in os.environ.items() if not key.startswith("RP_")}


def stop(process):
    """End a process started in its own session, with everything it started."""
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


class AutomationInfo(unittest.TestCase):
    def test_reads_what_the_launcher_exported(self):
        with mock.patch.dict(os.environ, LAUNCHED):
            self.assertEqual(rp_release.automation_info(), RECORDED)

    def test_is_none_outside_the_launcher(self):
        with mock.patch.dict(os.environ, without_launcher_variables(), clear=True):
            self.assertIsNone(rp_release.automation_info())


class StartingServerLog(unittest.TestCase):
    """Whose log says who ran /rp release: the server whose Java process started the release."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)
        self.proc = self.root / "proc"
        self.server = self.root / "servers-mcme" / "mainworld"
        (self.server / "logs").mkdir(parents=True)
        (self.server / "logs" / "latest.log").write_text("", encoding="utf-8")
        self.log = str(self.server / "logs" / "latest.log")

    def process(self, pid, exe, parent, name="sh", cwd=None):
        """A process as /proc shows it: its program, its parent in stat, its working folder."""
        folder = self.proc / str(pid)
        folder.mkdir(parents=True)
        os.symlink(exe, folder / "exe")
        (folder / "stat").write_text(f"{pid} ({name}) S {parent} {pid} {pid} 0 -1 4194304", encoding="utf-8")
        if cwd:
            os.symlink(cwd, folder / "cwd")

    def find(self, pid):
        return rp_release.starting_server_log("FALLBACK", proc=str(self.proc), pid=pid)

    def started_by_mainworld(self):
        # As MCME-Architect starts a release: the server's java, the launcher's
        # shell (the wrapper by now), and rp-release.py
        self.process(100, "/usr/lib/jvm/java-25-openjdk-amd64/bin/java", 1, name="java", cwd=self.server)
        self.process(200, "/usr/bin/dash", 100)
        self.process(300, "/usr/bin/python3.12", 200, name="python3")

    def test_finds_the_log_of_the_server_whose_java_started_the_release(self):
        self.started_by_mainworld()
        self.assertEqual(self.find(300), self.log)

    def test_a_process_name_with_brackets_and_spaces_still_leads_to_its_parent(self):
        self.process(100, "/usr/lib/jvm/java-25-openjdk-amd64/bin/java", 1, name="java", cwd=self.server)
        self.process(200, "/usr/bin/dash", 100, name="odd (name) here")
        self.assertEqual(self.find(200), self.log)

    def test_no_java_among_the_parents_falls_back(self):
        self.process(200, "/usr/bin/dash", 1)
        self.process(300, "/usr/bin/python3.12", 200, name="python3")
        self.assertEqual(self.find(300), "FALLBACK")

    def test_a_server_without_a_log_falls_back(self):
        self.started_by_mainworld()
        (self.server / "logs" / "latest.log").unlink()
        self.assertEqual(self.find(300), "FALLBACK")

    def test_a_parent_that_is_gone_falls_back(self):
        self.process(300, "/usr/bin/python3.12", 200, name="python3")
        self.assertEqual(self.find(300), "FALLBACK")

    def test_auto_outside_a_server_reads_the_folder_relative_log(self):
        # This test's parents hold no java: as on the RP server, where the
        # automation folder lies inside the server's folder
        self.assertEqual(rp_release.server_log_path("auto"), "../logs/latest.log")

    def test_a_named_log_is_used_as_it_is(self):
        self.assertEqual(rp_release.server_log_path("/srv/logs/latest.log"), "/srv/logs/latest.log")

    def test_the_user_comes_from_the_starting_servers_log(self):
        self.started_by_mainworld()
        Path(self.log).write_text(
            "[09:27:59] [Server thread/INFO]: Toti issued server command: /rp release h v4.1.3 Human\n"
            "[09:28:01] [Server thread/INFO]: Nicky issued server command: /rp release h v4.1.4 Human\n",
            encoding="utf-8",
        )
        at = datetime.datetime(2026, 10, 13, 9, 29, 0)
        self.assertEqual(rp_release.find_user(self.find(300), "v4.1.3", at), "Toti")
        self.assertEqual(rp_release.find_user(self.find(300), "v4.1.4", at), "Nicky")
        self.assertIsNone(rp_release.find_user(self.find(300), "v9.9.9", at))


class Records(unittest.TestCase):
    """rp-release.py log, then summary, as run.sh calls them."""

    def setUp(self):
        self.runs = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.runs, True)
        self.run_id = "20261010-120000-Rohan-v1.0"

    def record(self, env):
        """The run's #meta line and its summary."""
        tool = [sys.executable, str(RP_RELEASE)]
        subprocess.run(
            [*tool, "log", "--runs", str(self.runs), "--id", self.run_id, "--script", "releaseGeneral.sh", "--", *ARGS],
            input=b"compiling Rohan RP zips\n", capture_output=True, env=env, check=True,
        )
        meta_line = (self.runs / f"{self.run_id}.log").read_text(encoding="utf-8").splitlines()[0]
        subprocess.run(
            [*tool, "summary", "--runs", str(self.runs), "--id", self.run_id, "--exit", "0"],
            capture_output=True, env=env, check=True,
        )
        summary = json.loads((self.runs / f"{self.run_id}.json").read_text(encoding="utf-8"))
        return json.loads(meta_line[len("#meta "):]), summary

    def test_the_log_and_the_summary_record_what_the_launcher_released_with(self):
        meta, summary = self.record(dict(without_launcher_variables(), **LAUNCHED))
        self.assertEqual(meta["automation"], RECORDED)
        self.assertEqual(summary["automation"], RECORDED)

    def test_a_run_outside_the_launcher_records_none(self):
        _, summary = self.record(without_launcher_variables())
        self.assertIsNone(summary["automation"])

    def test_the_summary_keeps_its_version(self):
        # A field is added, nothing changes: the dashboard reads version-2 summaries
        _, summary = self.record(dict(without_launcher_variables(), **LAUNCHED))
        self.assertEqual(summary["version"], 2)


@unittest.skipUnless(TOOLS_PRESENT, "needs Linux with sh, flock and python3, as on the server")
class Wrapper(unittest.TestCase):
    """run.sh, started as the launcher starts it."""

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.folder, True)
        (self.folder / "runs").mkdir()
        self.script = self.folder / "releaseGeneral.sh"
        self.script.write_text(FAKE_RELEASE)

    def run_wrapper(self, prefix=UNDER_THE_LOCK, **env):
        """run.sh with ARGS, started by the shell code in prefix (None: run.sh by itself)."""
        command = ["sh", str(RUN_SH), str(self.script), *ARGS]
        if prefix:
            command = ["sh", "-c", prefix, "sh", *command[1:]]
        return subprocess.run(
            command, cwd=self.folder, capture_output=True, text=True,
            env=dict(without_launcher_variables(), **LAUNCHED, **env), timeout=60,
        )

    def summaries(self):
        return [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted((self.folder / "runs").glob("*.json"))
            if path.name[:1].isdigit()
        ]

    def write_progress(self, run_id):
        """runs/current.json and the run's log, as a run writes them while it runs, and leaves them when stopped."""
        runs = self.folder / "runs"
        meta = {"id": run_id, "script": "releaseVanillaSodium.sh", "pack": "Human", "tag": "v4.1.3"}
        (runs / "current.json").write_text(json.dumps({**meta, "updated": "2026-10-10T12:05:00+02:00"}))
        (runs / f"{run_id}.log").write_text(
            "#meta " + json.dumps(meta) + "\n2026-10-10T12:00:00.000 compiling Human RP zips\n"
        )

    def test_runs_the_release_and_writes_its_summary(self):
        result = self.run_wrapper()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("compiling Rohan RP zips", result.stdout)
        [summary] = self.summaries()
        self.assertRegex(summary["id"], r"^\d{8}-\d{6}-Rohan-v1\.0$")
        self.assertEqual(
            (summary["script"], summary["pack"], summary["tag"], summary["name"]),
            ("releaseGeneral.sh", "Rohan", "v1.0", "Better leaves"),
        )
        self.assertIn(f"Release run {summary['id']}: ", result.stdout)
        self.assertFalse((self.folder / "runs" / "current.json").exists())

    def test_prints_the_verdict_line_mcme_architect_reads(self):
        # Its whole shape is a contract (docs/release-pipeline.md, What MCME-Architect reads)
        result = self.run_wrapper()
        [summary] = self.summaries()
        self.assertRegex(result.stdout, r"(?m)^Release run " + re.escape(summary["id"]) + r": "
                         r"(OK|OK with warnings|FAILED|INTERRUPTED), (released|nothing released|cut off)\. "
                         r"\d+ warning\(s\), \d+ error\(s\)\.")

    def test_records_what_the_launcher_released_with(self):
        self.run_wrapper()
        [summary] = self.summaries()
        self.assertEqual(summary["automation"], RECORDED)

    def test_hands_the_script_its_run_id(self):
        result = self.run_wrapper()
        [summary] = self.summaries()
        self.assertIn(f"run {summary['id']}\n", result.stdout)

    def test_keeps_the_launchers_lock_while_the_script_runs(self):
        self.assertIn("lock probe: 1", self.run_wrapper().stdout)

    def test_runs_the_script_without_descriptor_9(self):
        # The wrapper holds the lock for it; nothing the script starts can keep it afterwards
        self.assertIn("descriptor 9: closed", self.run_wrapper().stdout)

    def test_passes_the_scripts_exit_code_on(self):
        result = self.run_wrapper(FAKE_EXIT="7")
        self.assertEqual(result.returncode, 7)
        [summary] = self.summaries()
        self.assertEqual(summary["exitCode"], 7)

    def test_refuses_to_run_without_the_launchers_lock(self):
        result = self.run_wrapper(prefix=None)
        self.assertEqual(result.returncode, 2)
        self.assertIn("only runs under the release launcher", result.stdout)
        self.assertNotIn("compiling", result.stdout)
        self.assertEqual(self.summaries(), [])

    def test_refuses_a_descriptor_9_that_is_another_file(self):
        # runs/.lock exists, so only the check that descriptor 9 is that very file can refuse
        (self.folder / "runs" / ".lock").touch()
        result = self.run_wrapper(prefix='exec 9>>other.lock && flock -n 9 && exec sh "$@"')
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("compiling", result.stdout)

    def test_refuses_the_release_lock_held_by_another_process(self):
        # Descriptor 9 is runs/.lock, but another process holds its lock. The release holding it owns
        # runs/current.json and its log: the refusal comes before anything touches them
        running = "20261010-120000-Human-v4.1.3"
        self.write_progress(running)
        runs = self.folder / "runs"
        before = {name: (runs / name).read_bytes() for name in ("current.json", f"{running}.log")}
        holder = subprocess.Popen(
            ["flock", str(self.folder / "runs" / ".lock"), "sh", "-c", "echo held; sleep 30"],
            stdout=subprocess.PIPE, text=True, start_new_session=True,
        )
        self.addCleanup(holder.stdout.close)
        self.addCleanup(stop, holder)
        self.assertEqual(holder.stdout.readline(), "held\n")
        result = self.run_wrapper(prefix='exec 9>>runs/.lock && exec sh "$@"')
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("compiling", result.stdout)
        self.assertEqual({name: (runs / name).read_bytes() for name in before}, before)
        self.assertEqual(self.summaries(), [])

    def test_closes_the_summary_of_a_run_that_was_stopped(self):
        # Architect stopped it, or the server went down: its log and progress were left behind
        stale = "20261010-120000-Human-v4.1.3"
        self.write_progress(stale)
        self.run_wrapper()
        closed = json.loads((self.folder / "runs" / f"{stale}.json").read_text(encoding="utf-8"))
        self.assertEqual(closed["status"], "interrupted")
        # From the stopped run's #meta line, which has none, not from this run's launcher settings
        self.assertIsNone(closed["automation"])


if __name__ == "__main__":
    unittest.main()
