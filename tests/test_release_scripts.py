"""Tests for the release scripts in automation/scripts/, run as the launcher
runs them: `sh <script> <Pack> <owner> <repo> <tag> <title>` in the automation
folder, with the folder's settings in RP_AUTOMATION_*.

Linux only, as on the server, and plain unittest, so WSL can run it without
pytest. 7-Zip, gh, git and generateVanilla are stand-ins from
tests/release_helpers.py that log every call; zips.py and release_note.py are
the real ones.
"""

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
# The lines the wrapper reads as steps (P4)
STEP = RP_RELEASE.STEP

TOOLS_PRESENT = os.name == "posix" and all(shutil.which(tool) for tool in ("sh", "python3"))
FOOTPRINTS = {"activator_rail.png": b"footprints rail", "activator_rail_on.png": b"footprints rail, powered"}
VANILLA_MCMETA = {"pack": {"min_format": 88, "max_format": 97, "description": "a vanilla-only pack"}}
SODIUM_MCMETA = {"pack": {"pack_format": 15, "supported_formats": [15, 255], "description": "a Sodium pack"}}
ROHAN = ("Rohan", "MCME", "RP-Rohan", "v1.0", "Better leaves")


@unittest.skipUnless(TOOLS_PRESENT, "needs Linux with sh and python3, as on the server")
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
            PATH=f"{self.tmp / 'bin'}:{os.environ['PATH']}",
            FAKE_LOG=str(self.log),
            FAKE_GH_RELEASES=str(self.tmp / "releases.txt"),
            RP_AUTOMATION_SIDE="test",
            RP_AUTOMATION_BRANCH="development",
            RP_AUTOMATION_REPLACE_EXISTING="yes",
            RP_AUTOMATION_COMMIT="0123456789abcdef0123456789abcdef01234567",
        )

    def make_pack(self, name, mcmeta, files=None):
        """A pack checkout in the folder: pack.mcmeta, its activator rail texture, and files ({path: bytes})."""
        pack = self.folder / name
        textures = pack / "assets" / "minecraft" / "textures" / "block"
        textures.mkdir(parents=True)
        (pack / "pack.mcmeta").write_text(json.dumps(mcmeta))
        (textures / "activator_rail.png").write_bytes(b"pack rail")
        for path, data in (files or {}).items():
            (pack / path).parent.mkdir(parents=True, exist_ok=True)
            (pack / path).write_bytes(data)
        return pack

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

    def test_asks_github_first_then_pulls_the_pack(self):
        self.release("releaseGeneral.sh", *ROHAN)
        first, second = self.calls()[:2]
        self.assertEqual((first["tool"], first["args"][:2]), ("gh", ["release", "view"]))
        self.assertEqual((second["tool"], second["args"], second["cwd"]), ("git", ["pull"], "Rohan-Vanilla"))

    def test_pulls_the_pack_without_the_lock_and_without_prompting(self):
        # Under the launcher descriptor 9 is the release lock: a detached git maintenance must not keep it.
        # A pull that wants a password must fail at once, not wait for Architect's 30 minutes
        result = self.release("releaseGeneral.sh", *ROHAN, prefix='exec 9>>runs/.lock && exec sh "$@"')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        [pull] = self.calls("git")
        self.assertEqual((pull["fd9"], pull["prompt"]), (False, "0"))
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
        textures = self.folder / "Rohan-Vanilla" / "assets" / "minecraft" / "textures" / "block"
        for name, data in FOOTPRINTS.items():
            (textures / name).write_bytes(data)
        result = self.release("releaseGeneral.sh", *ROHAN)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Rohan-Footprints.zip holds the same files as Rohan.zip", result.stderr)
        self.assertEqual(self.gh("create"), [])

    def test_a_failed_pull_of_the_pack_carries_on(self):
        # Unchanged on purpose: the release builds what the checkout has (item 1 changes that)
        result = self.release("releaseGeneral.sh", *ROHAN, FAKE_GIT_FAIL="1")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Could not resolve host", result.stderr)
        self.assertEqual(len(self.gh("upload")), 1)

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
        (self.folder / "Rohan-Vanilla" / "pack.mcmeta").write_text('{"pack": {"description": "no format"}}')
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
        # The wrapper sets RP_RELEASE_RUN and keeps --debug's lines out of the console; Lite never had them
        self.release("releaseVanillaSodium.sh", *HUMAN, RP_RELEASE_RUN="20261010-120000-Human-v4.1.3")
        vanilla, lite = [call["args"] for call in self.calls("generateVanilla")]
        self.assertEqual(vanilla[-1], "--debug")
        self.assertNotIn("--debug", lite)

    def test_does_not_pull_resourcepackscripts(self):
        # The launcher brought it up to date before the release started
        self.release("releaseVanillaSodium.sh", *HUMAN)
        self.assertEqual([call["cwd"] for call in self.calls("git")], ["Human-Sodium"])

    def test_names_the_minecraft_versions_all_six_zips_support(self):
        # The Sodium zips declare 15-255, the converted ones 88-97: the same versions, so no warning
        result = self.release("releaseVanillaSodium.sh", *HUMAN)
        [create] = self.gh("create")
        self.assertIn("--notes=Version v4.1.3 for Minecraft 26.2 and 26.3", create)
        self.assertNotIn("WARNING!!! release note", result.stdout)

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
        textures = self.folder / "Human-Sodium" / "assets" / "minecraft" / "textures" / "block"
        (textures / "activator_rail.png").write_bytes(FOOTPRINTS["activator_rail.png"])
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

    def test_pulls_the_checkout_named_after_the_pack(self):
        self.release("releaseDynmap.sh", *GONDOR)
        self.assertEqual([call["cwd"] for call in self.calls("git")], ["Gondor"])

    def test_replaces_the_zip_already_there(self):
        (self.texturepacks / "Gondor.zip").write_bytes(b"the last one")
        self.release("releaseDynmap.sh", *GONDOR)
        self.assertTrue(zipfile.is_zipfile(self.texturepacks / "Gondor.zip"))

    def test_stops_where_there_is_no_dynmap_folder(self):
        # P5: the production folder sits in the network folder, with no ../../baseline-server
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
