"""Tests for the release scripts in automation/scripts/, run as the launcher
runs them: `sh <script> <Pack> <owner> <repo> <tag> <title>` in the automation
folder, with the folder's settings in RP_AUTOMATION_*.

Linux only, as on the server, and plain unittest, so WSL can run it without
pytest. 7-Zip, gh and generateVanilla are stand-ins from
tests/release_helpers.py that log every call. git is the real one, behind a
stand-in that logs its calls, and each pack checkout is a clone of a local
repository that plays GitHub. zips.py and release_note.py are the real ones.
"""

import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = REPO_ROOT / "automation" / "scripts"
sys.path.insert(0, str(Path(__file__).resolve().parent))

import release_helpers  # noqa: E402

# The wrapper's rp-release.py, for the patterns it reads the output with
RP_RELEASE = release_helpers.load_rp_release()
# The lines the wrapper reads as steps, which the scripts must print exactly
STEP = RP_RELEASE.STEP

TOOLS_PRESENT = os.name == "posix" and all(shutil.which(tool) for tool in ("sh", "git", "python3"))
FOOTPRINTS = {"activator_rail.png": b"footprints rail", "activator_rail_on.png": b"footprints rail, powered"}
VANILLA_MCMETA = {"pack": {"min_format": 88, "max_format": 97, "description": "a vanilla-only pack"}}
SODIUM_MCMETA = {"pack": {"pack_format": 15, "supported_formats": [15, 255], "description": "a Sodium pack"}}
ROHAN = ("Rohan", "MCME", "RP-Rohan", "v1.0", "Better leaves")

# git as on the server, with nothing from the developer's own config
GIT_CONFIG = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
# The tests' own git: commits a pack developer pushes to GitHub, or an admin makes on the server. No GIT_*
# from the developer's environment: a GIT_DIR or GIT_INDEX_FILE from a git hook would point it at their repository
GIT_ENV = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
GIT_ENV.update(
    GIT_CONFIG,
    GIT_AUTHOR_NAME="test", GIT_AUTHOR_EMAIL="test@example.com",
    GIT_COMMITTER_NAME="test", GIT_COMMITTER_EMAIL="test@example.com",
)


def git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, env=GIT_ENV, check=True, capture_output=True)


def git_output(*args, cwd):
    result = subprocess.run(["git", *args], cwd=cwd, env=GIT_ENV, check=True, capture_output=True, text=True)
    return result.stdout.strip()


@unittest.skipUnless(TOOLS_PRESENT, "needs Linux with sh, git and python3, as on the server")
class ReleaseScriptTest(unittest.TestCase):
    """A throwaway automation folder inside a server folder, with Footprints/, Vanilla-26.2/ and runs/."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.folder = self.tmp / "network" / "rpserver" / "resourcePackAutomation"
        generate = self.folder / "ResourcePackScripts" / "generateVanilla"
        generate.mkdir(parents=True)
        (generate / "generateVanilla.py").write_text(release_helpers.FAKE_GENERATE)
        (generate / "objmc.py").write_text("")
        (self.folder / "Footprints").mkdir()
        for name, data in FOOTPRINTS.items():
            (self.folder / "Footprints" / name).write_bytes(data)
        (self.folder / "Vanilla-26.2").mkdir()
        (self.folder / "runs").mkdir()
        self.log = self.tmp / "calls.jsonl"
        release_helpers.install_fakes(self.tmp / "bin")
        # Nothing from the developer's environment: a GIT_TERMINAL_PROMPT=0 there would pass the prompt test by itself
        self.env = {key: value for key, value in os.environ.items() if not key.startswith(("RP_", "FAKE_", "GIT_"))}
        self.env.update(
            GIT_CONFIG,
            PATH=f"{self.tmp / 'bin'}:{os.environ['PATH']}",
            FAKE_LOG=str(self.log),
            FAKE_GH_RELEASES=str(self.tmp / "releases.txt"),
            RP_AUTOMATION_SIDE="test",
            RP_AUTOMATION_BRANCH="development",
            RP_AUTOMATION_REPLACE_EXISTING="yes",
            RP_AUTOMATION_COMMIT="0123456789abcdef0123456789abcdef01234567",
        )

    def make_pack(self, name, mcmeta, files=None):
        """A pack on "GitHub" with pack.mcmeta, its activator rail texture and files ({path: bytes}), and
        the server's checkout of it in the folder, on development. Returns the checkout."""
        seed = self.tmp / "seeds" / name
        textures = seed / "assets" / "minecraft" / "textures" / "block"
        textures.mkdir(parents=True)
        (seed / "pack.mcmeta").write_text(json.dumps(mcmeta))
        (textures / "activator_rail.png").write_bytes(b"pack rail")
        for path, data in (files or {}).items():
            (seed / path).parent.mkdir(parents=True, exist_ok=True)
            (seed / path).write_bytes(data)
        git("init", "-q", "-b", "development", str(seed), cwd=self.tmp)
        git("add", "-A", cwd=seed)
        git("commit", "-q", "-m", name, cwd=seed)
        github = self.tmp / "github" / f"{name}.git"
        git("clone", "-q", "--bare", str(seed), str(github), cwd=self.tmp)
        git("remote", "add", "origin", str(github), cwd=seed)
        git("clone", "-q", "-b", "development", str(github), str(self.folder / name), cwd=self.tmp)
        return self.folder / name

    def push_to_github(self, name, files, branch="development"):
        """Commit files ({path: bytes}) to the pack on "GitHub", as a pack developer does."""
        seed = self.tmp / "seeds" / name
        for path, data in files.items():
            (seed / path).parent.mkdir(parents=True, exist_ok=True)
            (seed / path).write_bytes(data)
        git("add", "-A", cwd=seed)
        git("commit", "-q", "-m", "on GitHub", cwd=seed)
        git("push", "-q", "origin", f"HEAD:{branch}", cwd=seed)

    def commit_on_the_server(self, checkout):
        """A commit made in the server's checkout, which GitHub doesn't have."""
        (checkout / "local.png").write_bytes(b"committed on the server")
        git("add", "local.png", cwd=checkout)
        git("commit", "-q", "-m", "a commit made on the server", cwd=checkout)

    def unreachable_github(self, checkout):
        """GitHub can't be reached from the checkout: its remote is a repository that isn't there."""
        git("remote", "set-url", "origin", str(self.tmp / "gone.git"), cwd=checkout)

    def existing_release(self, repo, tag):
        with open(self.tmp / "releases.txt", "a") as releases:
            print(f"{repo}@{tag}", file=releases)

    def release(self, script, *args, prefix=None, **env):
        """Run a release script in the folder. An env value of None unsets that variable. prefix is
        shell code that starts it, as the launcher hands over: exec sh "$@"."""
        command = ["sh", str(SCRIPTS / script), *args]
        if prefix:
            command = ["sh", "-c", prefix, "sh", *command[1:]]
        merged = {**self.env, **env}
        return subprocess.run(
            command, cwd=self.folder, capture_output=True, text=True, timeout=60,
            env={key: value for key, value in merged.items() if value is not None},
        )

    def calls(self, tool=None):
        return release_helpers.calls(self.log, tool)

    def gh(self, command):
        """The arguments of every `gh release <command>` call."""
        return [call["args"] for call in self.calls("gh") if call["args"][1] == command]

    def names_in(self, zip_path):
        with zipfile.ZipFile(self.folder / zip_path) as archive:
            return sorted(archive.namelist())

    def read_in(self, zip_path, member):
        with zipfile.ZipFile(self.folder / zip_path) as archive:
            return archive.read(member)

    def steps(self, output):
        """The lines the wrapper reads as steps, in order."""
        return [line for line in output.splitlines() if STEP.match(line)]

    def errors(self, result):
        """The ERROR: lines of a run: a stop prints exactly one."""
        return [line for line in result.stderr.splitlines() if line.startswith("ERROR: ")]


class ReleaseGeneral(ReleaseScriptTest):
    def setUp(self):
        super().setUp()
        self.make_pack("Rohan-Vanilla", VANILLA_MCMETA, {"inventories/blocks.json": b"{}", ".gitignore": b"*.obj"})

    def test_builds_both_zips_and_publishes_them(self):
        result = self.release("releaseGeneral.sh", *ROHAN)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(
            self.gh("upload"),
            [["release", "upload", "v1.0", "Rohan.zip", "Rohan-Footprints.zip", "--repo", "MCME/RP-Rohan", "--clobber"]],
        )
        self.assertIn("https://github.com/MCME/RP-Rohan/releases/tag/v1.0", result.stdout)
        # A new release: gh creates it, so there's no 422 to explain
        self.assertNotIn("already exists", result.stdout)

    def test_writes_the_release_note_from_the_zips(self):
        self.release("releaseGeneral.sh", *ROHAN)
        self.assertEqual(
            self.gh("create"),
            [["release", "create", "v1.0", "--repo", "MCME/RP-Rohan", "--title=Better leaves",
              "--notes=Version v1.0 for Minecraft 26.2 and 26.3"]],
        )

    def test_prints_the_release_note_before_publishing_for_mcme_architect(self):
        # MCME-Architect reads it for the /rp server buttons (docs/release-pipeline.md, What MCME-Architect reads)
        result = self.release("releaseGeneral.sh", *ROHAN)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        lines = result.stdout.splitlines()
        self.assertEqual([line for line in lines if line.startswith("release note: ")],
                         ["release note: Version v1.0 for Minecraft 26.2 and 26.3"])
        self.assertLess(lines.index("release note: Version v1.0 for Minecraft 26.2 and 26.3"),
                        lines.index("https://github.com/MCME/RP-Rohan/releases/tag/v1.0"))

    def test_zips_the_pack_without_its_inventories_or_top_level_dot_files(self):
        self.release("releaseGeneral.sh", *ROHAN)
        names = self.names_in("Rohan.zip")
        self.assertIn("pack.mcmeta", names)
        self.assertEqual([name for name in names if name.startswith(("inventories", "."))], [])

    def test_the_footprints_zip_has_both_footprints_textures(self):
        self.release("releaseGeneral.sh", *ROHAN)
        for name, data in FOOTPRINTS.items():
            with self.subTest(texture=name):
                self.assertEqual(self.read_in("Rohan-Footprints.zip", f"assets/minecraft/textures/block/{name}"), data)
        self.assertEqual(self.read_in("Rohan.zip", "assets/minecraft/textures/block/activator_rail.png"), b"pack rail")

    def test_prints_the_wrappers_step_lines_exactly(self):
        result = self.release("releaseGeneral.sh", *ROHAN)
        self.assertEqual(self.steps(result.stdout), ["compiling Rohan RP zips", "releasing Rohan RP zips"])

    def test_asks_github_first_then_updates_the_pack(self):
        self.release("releaseGeneral.sh", *ROHAN)
        first, second = self.calls()[:2]
        self.assertEqual((first["tool"], first["args"][:2]), ("gh", ["release", "view"]))
        self.assertEqual((second["tool"], second["repo"]), ("git", "Rohan-Vanilla"))

    def test_updates_the_pack_without_the_lock_and_without_prompting(self):
        # Under the launcher descriptor 9 is the release lock: a detached git maintenance must not keep it.
        # A fetch that wants a password must fail at once, and one that stalls (under 1000 bytes/s for 60 s)
        # must give up, not wait for Architect's 30 minutes
        result = self.release("releaseGeneral.sh", *ROHAN, prefix='exec 9>>runs/.lock && exec sh "$@"')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual([call["args"] for call in self.calls("git") if call["fd9"]], [])
        [fetch] = [call for call in self.calls("git") if "fetch" in call["args"]]
        self.assertEqual((fetch["prompt"], fetch["lowSpeed"]), ("0", ["1000", "60"]))
        # 7-Zip did inherit descriptor 9, so the check above isn't vacuous
        self.assertTrue(all(call["fd9"] for call in self.calls("7z")))

    def test_refuses_an_unsafe_tag_before_anything_else(self):
        for tag in ("v1 0", "-v1", "../v1", ".v1", "v1;id", "", "v1/x", "v1.0é"):
            with self.subTest(tag=tag):
                result = self.release("releaseGeneral.sh", "Rohan", "MCME", "RP-Rohan", tag, "x")
                self.assertEqual(result.returncode, 1)
                self.assertIn("ERROR: The tag", result.stderr)
                self.assertEqual(self.calls(), [])

    def test_refuses_unsafe_pack_owner_and_repo_names(self):
        for pack, owner, repo in (
            ("../Rohan", "MCME", "RP-Rohan"), ("..", "MCME", "RP-Rohan"), ("Rohan", "MC ME", "RP-Rohan"), ("Rohan", "MCME", "-R"),
        ):
            with self.subTest(pack=pack, owner=owner, repo=repo):
                result = self.release("releaseGeneral.sh", pack, owner, repo, "v1.0", "x")
                self.assertEqual(result.returncode, 1)
                self.assertIn("ERROR: The ", result.stderr)
                self.assertEqual(self.calls(), [])

    def test_needs_all_five_arguments(self):
        result = self.release("releaseGeneral.sh", "Rohan", "MCME", "RP-Rohan", "v1.0")
        self.assertEqual(result.returncode, 1)
        self.assertIn("takes <pack> <owner> <repo> <tag> <title>", result.stderr)
        self.assertEqual(self.calls(), [])

    def test_passes_an_awkward_title_intact(self):
        title = "it's \"quoted\" $HOME `id` -x"
        result = self.release("releaseGeneral.sh", "Rohan", "MCME", "RP-Rohan", "v1.0", title)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        [create] = self.gh("create")
        self.assertIn(f"--title={title}", create)

    def test_needs_the_launcher(self):
        # Started straight from the checkout it would hold no lock and read no automation.conf,
        # and the release that is running keeps its record
        current = self.folder / "runs" / "current"
        current.write_text("releaseVanillaSodium.sh Human MCME RP-Human v4.1.3 Leaves (started 2026-10-10 12:00:00)\n")
        result = self.release("releaseGeneral.sh", *ROHAN, RP_AUTOMATION_REPLACE_EXISTING=None)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Start releases with the launcher", result.stderr)
        self.assertEqual(self.calls(), [])
        self.assertTrue(current.exists())

    def test_refuses_an_existing_release_before_building_when_replacing_is_off(self):
        self.existing_release("MCME/RP-Rohan", "v1.0")
        result = self.release("releaseGeneral.sh", *ROHAN, RP_AUTOMATION_REPLACE_EXISTING="no")
        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "ERROR: v1.0 already exists in MCME/RP-Rohan, and this folder never replaces a release's zips", result.stderr
        )
        self.assertEqual([call["tool"] for call in self.calls()], ["gh"])
        self.assertFalse((self.folder / "release").exists())

    def test_replaces_the_zips_of_an_existing_release_when_replacing_is_on(self):
        self.existing_release("MCME/RP-Rohan", "v1.0")
        result = self.release("releaseGeneral.sh", *ROHAN)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        # What the wrapper reads as "the release already existed"
        self.assertIn("Release.tag_name already exists", result.stderr)
        [upload] = self.gh("upload")
        self.assertEqual(upload[-1], "--clobber")

    def test_says_why_gh_answers_422_when_replacing(self):
        # gh release create still runs, since the wrapper reads its 422 as "the release already existed".
        # The line before it says so in words the wrapper counts as neither an error nor that 422
        self.existing_release("MCME/RP-Rohan", "v1.0")
        result = self.release("releaseGeneral.sh", *ROHAN)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        line = "v1.0 already exists in MCME/RP-Rohan: its zips are replaced (replace_existing=yes). gh's 422 below is expected."
        self.assertIn(line + "\n", result.stdout)
        self.assertIsNone(RP_RELEASE.ERROR.search(line))
        self.assertIsNone(RP_RELEASE.TAG_EXISTS.search(line))
        self.assertEqual(len(self.gh("create")), 1)

    def test_never_clobbers_when_replacing_is_off(self):
        result = self.release("releaseGeneral.sh", *ROHAN, RP_AUTOMATION_REPLACE_EXISTING="no")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        [upload] = self.gh("upload")
        self.assertNotIn("--clobber", upload)

    def test_stops_when_gh_cannot_tell_whether_the_release_exists(self):
        result = self.release("releaseGeneral.sh", *ROHAN, FAKE_GH_FAIL="view")
        self.assertEqual(result.returncode, 1)
        self.assertIn("gh couldn't tell whether v1.0 exists in MCME/RP-Rohan: HTTP 502", result.stderr)
        self.assertEqual([call["tool"] for call in self.calls()], ["gh"])

    def test_stops_when_creating_the_release_fails(self):
        result = self.release("releaseGeneral.sh", *ROHAN, FAKE_GH_FAIL="create")
        self.assertEqual(result.returncode, 1)
        self.assertIn("gh couldn't create the release v1.0 in MCME/RP-Rohan", result.stderr)
        self.assertEqual(self.gh("upload"), [])

    def test_stops_when_the_upload_fails(self):
        # gh release create has published the new release, so it is on GitHub without all its zips
        result = self.release("releaseGeneral.sh", *ROHAN, FAKE_GH_FAIL="upload")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.errors(result), [
            "ERROR: gh couldn't upload every zip to the release v1.0 in MCME/RP-Rohan (see above). The release is on"
            " GitHub now, without all its zips: release again with the same tag to finish it."
        ])

    def test_stops_when_the_upload_fails_where_zips_are_never_replaced(self):
        # Production: the same tag would be refused, so the partial release has to go first
        result = self.release("releaseGeneral.sh", *ROHAN, RP_AUTOMATION_REPLACE_EXISTING="no", FAKE_GH_FAIL="upload")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.errors(result), [
            "ERROR: gh couldn't upload every zip to the release v1.0 in MCME/RP-Rohan (see above). The release is on"
            " GitHub now, without all its zips, and this folder never replaces a release's zips: delete the release"
            " (gh release delete v1.0 --repo MCME/RP-Rohan, or on its GitHub page), then release again, or use a"
            " new tag."
        ])

    def test_stops_when_the_upload_to_an_existing_release_fails(self):
        # Replacing: the upload may have replaced some zips and not others
        self.existing_release("MCME/RP-Rohan", "v1.0")
        result = self.release("releaseGeneral.sh", *ROHAN, FAKE_GH_FAIL="upload")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.errors(result), [
            "ERROR: gh couldn't upload every zip to the release v1.0 in MCME/RP-Rohan (see above). The release"
            " existed before, so some of its zips may still be the earlier release's: release again with the same"
            " tag to replace them all."
        ])

    def test_stops_when_a_footprints_texture_is_missing(self):
        (self.folder / "Footprints" / "activator_rail_on.png").unlink()
        result = self.release("releaseGeneral.sh", *ROHAN)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Couldn't copy Footprints/activator_rail_on.png", result.stderr)
        self.assertEqual(self.gh("create"), [])

    def test_stops_when_the_footprints_zip_holds_the_same_files(self):
        # The pack has the footprints textures already, so the copy changes nothing
        self.push_to_github("Rohan-Vanilla", {
            f"assets/minecraft/textures/block/{name}": data for name, data in FOOTPRINTS.items()
        })
        result = self.release("releaseGeneral.sh", *ROHAN)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Rohan-Footprints.zip holds the same files as Rohan.zip", result.stderr)
        self.assertEqual(self.gh("create"), [])

    def test_stops_when_the_pack_has_no_checkout_here(self):
        result = self.release("releaseGeneral.sh", "Gondor", "MCME", "RP-Gondor", "v1.0", "x")
        self.assertEqual(result.returncode, 1)
        self.assertIn("There's no Gondor-Vanilla checkout in this folder", result.stderr)
        self.assertEqual(self.calls(), [])

    def test_stops_when_7zip_fails(self):
        result = self.release("releaseGeneral.sh", *ROHAN, FAKE_7Z_FAIL="Rohan-Footprints.zip")
        self.assertEqual(result.returncode, 1)
        self.assertIn("7-Zip couldn't make Rohan-Footprints.zip", result.stderr)
        self.assertEqual(self.gh("create"), [])

    def test_a_7zip_warning_is_passed_on(self):
        result = self.release("releaseGeneral.sh", *ROHAN, FAKE_7Z_WARN="Rohan.zip")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("WARNING!!! 7-Zip had a problem with some files of Rohan.zip", result.stdout)

    def test_never_publishes_a_zip_left_by_an_earlier_release(self):
        (self.folder / "Rohan-Footprints.zip").write_bytes(b"the last release's zip")
        result = self.release("releaseGeneral.sh", *ROHAN, FAKE_7Z_FAIL="Rohan-Footprints.zip")
        self.assertEqual(result.returncode, 1)
        self.assertFalse((self.folder / "Rohan-Footprints.zip").exists())
        self.assertEqual(self.gh("upload"), [])

    def test_stops_when_the_release_note_cannot_be_worked_out(self):
        self.push_to_github("Rohan-Vanilla", {"pack.mcmeta": b'{"pack": {"description": "no format"}}'})
        result = self.release("releaseGeneral.sh", *ROHAN)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Couldn't work out the release note", result.stderr)
        self.assertEqual(self.gh("create"), [])

    def test_clears_the_launchers_record_when_it_ends(self):
        # Released or stopped, the release is over: a release refused later must not name it
        current = self.folder / "runs" / "current"
        for env in ({}, {"FAKE_GH_FAIL": "view"}):
            with self.subTest(env=env):
                current.write_text("releaseGeneral.sh Rohan MCME RP-Rohan v1.0 Better leaves (started 2026-10-10 12:00:00)\n")
                self.release("releaseGeneral.sh", *ROHAN, **env)
                self.assertFalse(current.exists())


class PackCheckout(ReleaseScriptTest):
    """A release builds what GitHub has: the pack's checkout is brought up to date with its branch on
    GitHub, or the release stops before it builds anything. Through releaseGeneral.sh: all three scripts
    update their pack with common.sh's pull_pack."""

    EDITED = (
        "ERROR: Someone edited Rohan-Vanilla on the server (git status above): the release would build files"
        " that aren't on GitHub. Nothing was built. An admin takes the change to the pack's repository on"
        " GitHub, or undoes it here."
    )
    AHEAD = (
        "ERROR: Rohan-Vanilla has commits that GitHub's development doesn't: made on the server, or left behind"
        " when GitHub's history was rewritten. Nothing was built. An admin takes them to GitHub, or resets the"
        " checkout to GitHub's development."
    )
    # Not the folder's own branch: some packs build another one (docs/pack-repository.md)
    STAGE_BRANCH = "switches it to the branch this stage builds for the pack, which docs/pack-repository.md lists"

    def follows_no_branch(self, branch):
        return (
            f"ERROR: Rohan-Vanilla is on '{branch}', which follows no branch on GitHub: deleted there, made on the"
            f" server, or never connected. Nothing was built. An admin connects it to GitHub's '{branch}'"
            f" (git -C Rohan-Vanilla branch --set-upstream-to=origin/{branch}), or {self.STAGE_BRANCH}."
        )

    def setUp(self):
        super().setUp()
        self.pack = self.make_pack("Rohan-Vanilla", VANILLA_MCMETA)

    def assert_stopped(self, result, error):
        """Stopped with exactly this ERROR: line, before building or publishing anything."""
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(self.errors(result), [error])
        self.assertEqual(self.calls("7z"), [])
        self.assertEqual(self.gh("create"), [])

    def test_builds_what_github_has(self):
        self.push_to_github("Rohan-Vanilla", {"assets/minecraft/textures/block/stone.png": b"stone, pushed"})
        result = self.release("releaseGeneral.sh", *ROHAN)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.read_in("Rohan.zip", "assets/minecraft/textures/block/stone.png"), b"stone, pushed")

    def test_shows_what_the_update_changed_as_the_wrapper_reads_it(self):
        # The wrapper turns git's fetch and update lines into the run's git events on the dashboard
        self.push_to_github("Rohan-Vanilla", {"assets/minecraft/textures/block/stone.png": b"stone, pushed"})
        result = self.release("releaseGeneral.sh", *ROHAN)
        at = datetime.datetime(2026, 10, 11, 12, 0, 0)
        events, _ = RP_RELEASE.fold([(at, line) for line in result.stdout.splitlines()])
        [update] = [event for event in events if event["kind"] == "git"]
        self.assertIn("1 file changed", update["text"])
        # The wrapper reads the fetch's "From https://github.com/…" line; here GitHub is a local folder
        self.assertIn(f"From {self.tmp / 'github' / 'Rohan-Vanilla'}\n", result.stderr)

    def test_only_fast_forwards_whatever_the_servers_git_config_says(self):
        # With merge.ff=false a plain merge would make a merge commit on the server
        git("config", "merge.ff", "false", cwd=self.pack)
        self.push_to_github("Rohan-Vanilla", {"assets/minecraft/textures/block/stone.png": b"stone, pushed"})
        result = self.release("releaseGeneral.sh", *ROHAN)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        on_github = git_output("rev-parse", "development", cwd=self.tmp / "github" / "Rohan-Vanilla.git")
        self.assertEqual(git_output("rev-parse", "HEAD", cwd=self.pack), on_github)

    def test_stops_when_github_cannot_be_reached(self):
        self.unreachable_github(self.pack)
        result = self.release("releaseGeneral.sh", *ROHAN)
        self.assert_stopped(
            result,
            "ERROR: Couldn't fetch Rohan-Vanilla from GitHub (git's reason is above), so the release would build"
            " old files. Nothing was built. Try again in a few minutes. If it keeps failing, an admin fixes what"
            " git's reason names.",
        )
        # git's reason
        self.assertIn("does not appear to be a git repository", result.stderr)

    def test_stops_when_a_file_was_edited_on_the_server(self):
        (self.pack / "pack.mcmeta").write_text("edited on the server")
        result = self.release("releaseGeneral.sh", *ROHAN)
        self.assert_stopped(result, self.EDITED)
        # The admin sees which file changed, as git status shows it
        self.assertIn("What git status shows in Rohan-Vanilla:\n   M pack.mcmeta\n", result.stderr)

    def test_stops_when_a_file_was_added_on_the_server(self):
        # It would go into the zips too, whatever the server's git config says
        git("config", "status.showUntrackedFiles", "no", cwd=self.pack)
        (self.pack / "extra.png").write_bytes(b"added on the server")
        result = self.release("releaseGeneral.sh", *ROHAN)
        self.assert_stopped(result, self.EDITED)
        self.assertIn("\n  ?? extra.png\n", result.stderr)

    def test_shows_at_most_ten_of_the_changes(self):
        # Ten all fit
        for n in range(10):
            (self.pack / f"extra{n:02}.png").write_bytes(b"added on the server")
        result = self.release("releaseGeneral.sh", *ROHAN)
        self.assert_stopped(result, self.EDITED)
        shown = [line for line in result.stderr.splitlines() if line.startswith("  ?? extra")]
        self.assertEqual(shown, [f"  ?? extra{n:02}.png" for n in range(10)])
        self.assertNotIn(" more: ", result.stderr)
        # Twelve: the first ten, and how many more
        for n in range(10, 12):
            (self.pack / f"extra{n:02}.png").write_bytes(b"added on the server")
        result = self.release("releaseGeneral.sh", *ROHAN)
        self.assert_stopped(result, self.EDITED)
        shown = [line for line in result.stderr.splitlines() if line.startswith("  ?? extra")]
        self.assertEqual(shown, [f"  ?? extra{n:02}.png" for n in range(10)])
        self.assertIn("\n  and 2 more: git -C Rohan-Vanilla status lists them all.\n", result.stderr)

    def test_stops_when_a_commit_was_made_on_the_server(self):
        # GitHub hasn't moved, so a fast-forward alone would call this "already up to date"
        self.commit_on_the_server(self.pack)
        result = self.release("releaseGeneral.sh", *ROHAN)
        self.assert_stopped(result, self.AHEAD)

    def test_stops_when_the_checkout_has_diverged_from_github(self):
        self.commit_on_the_server(self.pack)
        self.push_to_github("Rohan-Vanilla", {"assets/minecraft/textures/block/stone.png": b"stone, pushed"})
        result = self.release("releaseGeneral.sh", *ROHAN)
        self.assert_stopped(result, self.AHEAD)

    def test_stops_when_the_checkout_is_not_on_a_branch(self):
        git("checkout", "-q", "--detach", cwd=self.pack)
        result = self.release("releaseGeneral.sh", *ROHAN)
        self.assert_stopped(
            result,
            "ERROR: Rohan-Vanilla isn't on a branch, so the release can't follow GitHub. Nothing was built. An admin"
            f" {self.STAGE_BRANCH}: git -C Rohan-Vanilla switch <branch>",
        )

    def test_stops_when_github_no_longer_has_the_branch(self):
        # A branch tried on the server, then merged and deleted on GitHub: a plain fetch would keep its
        # last commit as origin/feature, and every release would build that
        self.push_to_github("Rohan-Vanilla", {"assets/minecraft/textures/block/stone.png": b"a feature"}, "feature")
        git("fetch", "-q", cwd=self.pack)
        git("switch", "-q", "feature", cwd=self.pack)
        git("push", "-q", "origin", "--delete", "feature", cwd=self.tmp / "seeds" / "Rohan-Vanilla")
        result = self.release("releaseGeneral.sh", *ROHAN)
        self.assert_stopped(result, self.follows_no_branch("feature"))

    def test_stops_when_the_branch_was_made_on_the_server(self):
        git("switch", "-q", "-c", "hotfix", cwd=self.pack)
        result = self.release("releaseGeneral.sh", *ROHAN)
        self.assert_stopped(result, self.follows_no_branch("hotfix"))

    def test_stops_when_the_branch_follows_a_branch_of_the_checkout_itself(self):
        # Its fetch would fetch nothing from GitHub, and the release would build the checkout's old development
        git("switch", "-q", "-c", "hotfix", "--track", "development", cwd=self.pack)
        self.push_to_github("Rohan-Vanilla", {"assets/minecraft/textures/block/stone.png": b"stone, pushed"})
        result = self.release("releaseGeneral.sh", *ROHAN)
        self.assert_stopped(result, self.follows_no_branch("hotfix"))

    def test_stops_when_the_folder_is_not_a_checkout(self):
        # A copy of the pack without its .git. Inside another repository, git would answer for that one
        shutil.rmtree(self.pack / ".git")
        result = self.release("releaseGeneral.sh", *ROHAN)
        self.assert_stopped(
            result,
            "ERROR: Rohan-Vanilla isn't a git checkout (it has no .git), so the release can't follow GitHub. Nothing"
            " was built. An admin checks the pack out again, as docs/server-setup.md says.",
        )

    def test_stops_when_git_cannot_read_the_checkout(self):
        # A broken .git, in a server folder that is a repository itself: git must not answer for that one,
        # which says nothing changed while it ignores everything
        git("init", "-q", str(self.tmp), cwd=self.tmp)
        (self.tmp / ".gitignore").write_text("*\n")
        (self.pack / ".git" / "HEAD").write_text("not a ref\n")
        result = self.release("releaseGeneral.sh", *ROHAN)
        self.assert_stopped(
            result,
            "ERROR: git can't read Rohan-Vanilla (its reason is above). Nothing was built. An admin repairs the"
            " checkout, or checks the pack out again.",
        )
        self.assertIn("not a git repository", result.stderr)

    def test_stops_when_git_status_fails(self):
        # Read as "nothing edited", a broken index would let the release build whatever is there
        (self.pack / ".git" / "index").write_bytes(b"not an index")
        result = self.release("releaseGeneral.sh", *ROHAN)
        self.assert_stopped(
            result,
            "ERROR: git status failed in Rohan-Vanilla (its reason is above). Nothing was built. An admin repairs"
            " the checkout, or checks the pack out again.",
        )

    @unittest.skipIf(os.name == "posix" and os.geteuid() == 0, "root can write a read-only folder")
    def test_stops_when_the_update_cannot_be_written(self):
        # For example a folder the server's user can't write to
        self.push_to_github("Rohan-Vanilla", {"assets/minecraft/textures/block/new.png": b"pushed"})
        textures = self.pack / "assets" / "minecraft" / "textures" / "block"
        textures.chmod(0o555)
        self.addCleanup(textures.chmod, 0o755)
        result = self.release("releaseGeneral.sh", *ROHAN)
        self.assert_stopped(
            result,
            "ERROR: Couldn't bring Rohan-Vanilla up to date with GitHub's development (git's reason is above)."
            " Nothing was built. An admin fixes what git's reason names, for example files that belong to another"
            " user.",
        )


class Publish(ReleaseScriptTest):
    """common.sh's publish on its own, in a script that never asked GitHub whether the release exists."""

    def setUp(self):
        super().setUp()
        checkout = self.tmp / "checkout"
        shutil.copytree(REPO_ROOT / "automation", checkout / "automation", ignore=shutil.ignore_patterns("__pycache__"))
        (checkout / "generateVanilla").mkdir()
        shutil.copy(REPO_ROOT / "generateVanilla" / "pack_formats.json", checkout / "generateVanilla")
        self.script = checkout / "automation" / "scripts" / "releasePublishOnly.sh"
        self.script.write_text('. "$(dirname "$0")/common.sh"\npublish "$pack.zip"\n')
        with zipfile.ZipFile(self.folder / "Rohan.zip", "w") as archive:
            archive.writestr("pack.mcmeta", json.dumps(VANILLA_MCMETA))

    def test_a_failed_create_stops_unless_the_release_is_known_to_exist(self):
        # Only a release gh said exists goes on to the upload after a failed create
        result = self.release(str(self.script), *ROHAN, FAKE_GH_FAIL="create")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.errors(result), [
            "ERROR: gh couldn't create the release v1.0 in MCME/RP-Rohan (see above). Nothing was uploaded."
        ])
        self.assertEqual(self.gh("upload"), [])


HUMAN = ("Human", "MCME", "RP-Human", "v4.1.3", "Better leaves")
SIX_ZIPS = [
    "Human-Vanilla.zip", "Human-Vanilla-Footprints.zip", "Human-Sodium.zip",
    "Human-Sodium-Footprints.zip", "Human-Lite.zip", "Human-Lite-Footprints.zip",
]


class ReleaseVanillaSodium(ReleaseScriptTest):
    def setUp(self):
        super().setUp()
        self.make_pack("Human-Sodium", SODIUM_MCMETA, {
            "vanilla/assets/minecraft/blockstates/stone.json": b"{}",
            "assets/mcme/models/block/tree.obj": b"v 0 0 0",
        })

    def test_builds_six_zips_and_publishes_them_in_the_usual_order(self):
        result = self.release("releaseVanillaSodium.sh", *HUMAN)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(
            self.gh("upload"), [["release", "upload", "v4.1.3", *SIX_ZIPS, "--repo", "MCME/RP-Human", "--clobber"]]
        )

    def test_prints_the_wrappers_step_lines_exactly(self):
        result = self.release("releaseVanillaSodium.sh", *HUMAN)
        self.assertEqual(self.steps(result.stdout), [
            "compiling Human RP zips", "Human-Sodium", "Human-Sodium-Footprints", "Human-Vanilla",
            "Human-Vanilla-Footprints", "Human-Lite", "Human-Lite-Footprints", "releasing Human RP zips",
        ])

    def test_the_sodium_zip_is_the_pack_without_its_vanilla_folder(self):
        self.release("releaseVanillaSodium.sh", *HUMAN)
        names = self.names_in("Human-Sodium.zip")
        self.assertIn("assets/mcme/models/block/tree.obj", names)
        self.assertEqual([name for name in names if name.startswith("vanilla")], [])

    def test_the_sodium_footprints_zip_swaps_only_the_unpowered_rail(self):
        # As it always has (docs: Known limits); the converted Footprints zips swap both
        self.release("releaseVanillaSodium.sh", *HUMAN)
        self.assertEqual(
            self.read_in("Human-Sodium-Footprints.zip", "assets/minecraft/textures/block/activator_rail.png"),
            FOOTPRINTS["activator_rail.png"],
        )
        on = "assets/minecraft/textures/block/activator_rail_on.png"
        self.assertNotIn(on, self.names_in("Human-Sodium-Footprints.zip"))
        self.assertIn(on, self.names_in("Human-Lite-Footprints.zip"))

    def test_converts_the_sodium_pack_with_the_26_2_assets(self):
        self.release("releaseVanillaSodium.sh", *HUMAN)
        vanilla, lite = [call["args"] for call in self.calls("generateVanilla")]
        common = ["Human-Sodium", "release", "Vanilla-26.2", "--objmc", "ResourcePackScripts/generateVanilla/objmc.py"]
        self.assertEqual(vanilla, common)
        self.assertEqual(lite, [*common, "--limit", "2"])

    def test_asks_for_debug_lines_only_under_the_wrapper(self):
        # The wrapper sets RP_RELEASE_RUN and keeps --debug's lines out of Architect's log; Lite never had them
        self.release("releaseVanillaSodium.sh", *HUMAN, RP_RELEASE_RUN="20261010-120000-Human-v4.1.3")
        vanilla, lite = [call["args"] for call in self.calls("generateVanilla")]
        self.assertEqual(vanilla[-1], "--debug")
        self.assertNotIn("--debug", lite)

    def test_updates_only_the_sodium_checkout(self):
        # The launcher brought ResourcePackScripts up to date before the release started
        self.release("releaseVanillaSodium.sh", *HUMAN)
        self.assertEqual({call["repo"] for call in self.calls("git")}, {"Human-Sodium"})

    def test_stops_before_building_when_github_cannot_be_reached(self):
        self.unreachable_github(self.folder / "Human-Sodium")
        result = self.release("releaseVanillaSodium.sh", *HUMAN)
        self.assertEqual(result.returncode, 1)
        [error] = self.errors(result)
        self.assertTrue(error.startswith("ERROR: Couldn't fetch Human-Sodium from GitHub"), error)
        self.assertEqual(self.calls("7z") + self.calls("generateVanilla"), [])
        self.assertEqual(self.gh("create"), [])

    def test_names_the_minecraft_versions_all_six_zips_support(self):
        # The Sodium zips declare 15-255, the converted ones 88-97: the same versions, so no warning
        result = self.release("releaseVanillaSodium.sh", *HUMAN)
        [create] = self.gh("create")
        self.assertIn("--notes=Version v4.1.3 for Minecraft 26.2 and 26.3", create)
        self.assertNotIn("WARNING!!! release note", result.stdout)

    def test_prints_the_release_note_for_mcme_architect(self):
        result = self.release("releaseVanillaSodium.sh", *HUMAN)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual([line for line in result.stdout.splitlines() if line.startswith("release note: ")],
                         ["release note: Version v4.1.3 for Minecraft 26.2 and 26.3"])

    def test_the_release_notes_warnings_count_as_warnings(self):
        result = self.release("releaseVanillaSodium.sh", *HUMAN, FAKE_GENERATE_FORMATS="97 97")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("WARNING!!! release note: the zips support different Minecraft versions", result.stdout)
        [create] = self.gh("create")
        self.assertIn("--notes=Version v4.1.3 for Minecraft 26.3", create)

    def test_stops_when_lite_holds_the_same_files_as_vanilla(self):
        # generateVanilla marks every Lite conversion, so the same files mean Lite mode didn't apply:
        # that Lite would be Vanilla under the Lite name
        result = self.release("releaseVanillaSodium.sh", *HUMAN, FAKE_GENERATE_SAME="1")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.errors(result), [
            "ERROR: Human-Lite.zip holds the same files as Human-Vanilla.zip: generateVanilla's Lite mode didn't"
            " apply, since every Lite conversion sets the shader base's MCME_LITE flag. Nothing was published."
        ])
        # It stopped in its own step
        self.assertEqual(self.steps(result.stdout)[-1], "Human-Lite")
        self.assertEqual(self.gh("create"), [])

    def test_stops_when_the_sodium_footprints_zip_holds_the_same_files(self):
        self.push_to_github("Human-Sodium", {
            "assets/minecraft/textures/block/activator_rail.png": FOOTPRINTS["activator_rail.png"],
        })
        result = self.release("releaseVanillaSodium.sh", *HUMAN)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Human-Sodium-Footprints.zip holds the same files as Human-Sodium.zip", result.stderr)
        # It stopped in its own step, before converting anything
        self.assertEqual(self.calls("generateVanilla"), [])
        self.assertEqual(self.gh("create"), [])

    def test_stops_when_the_vanilla_footprints_zip_holds_the_same_files(self):
        # Both conversions come out with the footprints textures already in them
        result = self.release("releaseVanillaSodium.sh", *HUMAN, FAKE_RAILS=str(self.folder / "Footprints"))
        self.assertEqual(result.returncode, 1)
        errors = [line for line in result.stderr.splitlines() if line.startswith("ERROR: ")]
        self.assertEqual(len(errors), 1, result.stderr)
        self.assertIn("Human-Vanilla-Footprints.zip holds the same files as Human-Vanilla.zip", errors[0])
        # It stopped in its own step, before the Lite conversion
        self.assertEqual(len(self.calls("generateVanilla")), 1)
        self.assertEqual(self.gh("create"), [])

    def test_stops_when_the_lite_footprints_zip_holds_the_same_files(self):
        # Only the Lite conversion comes out with the footprints textures, so Lite still differs from Vanilla
        result = self.release("releaseVanillaSodium.sh", *HUMAN, FAKE_LITE_RAILS=str(self.folder / "Footprints"))
        self.assertEqual(result.returncode, 1)
        errors = [line for line in result.stderr.splitlines() if line.startswith("ERROR: ")]
        self.assertEqual(len(errors), 1, result.stderr)
        self.assertIn("Human-Lite-Footprints.zip holds the same files as Human-Lite.zip", errors[0])
        self.assertEqual(len(self.calls("generateVanilla")), 2)
        self.assertEqual(self.gh("create"), [])

    def test_stops_when_generatevanilla_fails(self):
        result = self.release("releaseVanillaSodium.sh", *HUMAN, FAKE_GENERATE_FAIL="1")
        self.assertEqual(result.returncode, 1)
        self.assertIn("generateVanilla stopped", result.stderr)
        self.assertEqual(len(self.calls("generateVanilla")), 1)
        self.assertEqual(self.gh("create"), [])

    def test_stops_when_the_vanilla_assets_are_missing(self):
        # generateVanilla would find no blockstates, write none, and still end without an error
        (self.folder / "Vanilla-26.2").rmdir()
        result = self.release("releaseVanillaSodium.sh", *HUMAN)
        self.assertEqual(result.returncode, 1)
        self.assertIn("There's no Vanilla-26.2 folder here", result.stderr)
        self.assertEqual(self.calls(), [])

    def test_refuses_an_existing_release_before_building_when_replacing_is_off(self):
        self.existing_release("MCME/RP-Human", "v4.1.3")
        result = self.release("releaseVanillaSodium.sh", *HUMAN, RP_AUTOMATION_REPLACE_EXISTING="no")
        self.assertEqual(result.returncode, 1)
        self.assertIn("v4.1.3 already exists in MCME/RP-Human", result.stderr)
        self.assertEqual([call["tool"] for call in self.calls()], ["gh"])

    def test_stops_when_the_pack_has_no_sodium_checkout_here(self):
        result = self.release("releaseVanillaSodium.sh", "Mordor", "MCME", "RP-Mordor", "v1.0", "x")
        self.assertEqual(result.returncode, 1)
        self.assertIn("There's no Mordor-Sodium checkout in this folder", result.stderr)
        self.assertEqual(self.calls(), [])


GONDOR = ("Gondor", "MCME", "RP-Gondor", "v1.0", "Dynmap")


class ReleaseDynmap(ReleaseScriptTest):
    def setUp(self):
        super().setUp()
        self.make_pack("Gondor", VANILLA_MCMETA, {"inventories/blocks.json": b"{}"})
        # ../../baseline-server seen from the automation folder, as on the RP server
        self.texturepacks = self.tmp / "network" / "baseline-server" / "plugins" / "dynmap" / "texturepacks"
        self.texturepacks.mkdir(parents=True)

    def test_puts_the_zip_into_dynmaps_texture_packs(self):
        result = self.release("releaseDynmap.sh", *GONDOR)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        names = self.names_in(self.texturepacks / "Gondor.zip")
        self.assertIn("pack.mcmeta", names)
        self.assertEqual([name for name in names if name.startswith("inventories")], [])
        self.assertFalse((self.folder / "Gondor.zip").exists())

    def test_publishes_nothing(self):
        self.release("releaseDynmap.sh", *GONDOR)
        self.assertEqual(self.calls("gh"), [])

    def test_prints_the_wrappers_step_line_exactly(self):
        result = self.release("releaseDynmap.sh", *GONDOR)
        self.assertEqual(self.steps(result.stdout), ["compiling Gondor RP zips"])

    def test_updates_the_checkout_named_after_the_pack(self):
        self.release("releaseDynmap.sh", *GONDOR)
        self.assertEqual({call["repo"] for call in self.calls("git")}, {"Gondor"})

    def test_replaces_the_zip_already_there(self):
        (self.texturepacks / "Gondor.zip").write_bytes(b"the last one")
        self.release("releaseDynmap.sh", *GONDOR)
        self.assertTrue(zipfile.is_zipfile(self.texturepacks / "Gondor.zip"))

    def test_keeps_the_last_zip_when_github_cannot_be_reached(self):
        (self.texturepacks / "Gondor.zip").write_bytes(b"the last one")
        self.unreachable_github(self.folder / "Gondor")
        result = self.release("releaseDynmap.sh", *GONDOR)
        self.assertEqual(result.returncode, 1)
        [error] = self.errors(result)
        self.assertTrue(error.startswith("ERROR: Couldn't fetch Gondor from GitHub"), error)
        self.assertEqual((self.texturepacks / "Gondor.zip").read_bytes(), b"the last one")

    def test_stops_where_there_is_no_dynmap_folder(self):
        # The production folder sits in the network folder, with no ../../baseline-server
        shutil.rmtree(self.tmp / "network" / "baseline-server")
        result = self.release("releaseDynmap.sh", *GONDOR)
        self.assertEqual(result.returncode, 1)
        self.assertIn("There's no dynmap texture packs folder", result.stderr)
        self.assertEqual(self.calls(), [])

    def test_checks_its_arguments_like_the_others(self):
        result = self.release("releaseDynmap.sh", "..", "MCME", "RP-Gondor", "v1.0", "x")
        self.assertEqual(result.returncode, 1)
        self.assertIn("ERROR: The pack name", result.stderr)
        self.assertEqual(self.calls(), [])


if __name__ == "__main__":
    unittest.main()
