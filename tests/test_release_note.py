"""Tests for automation/release_note.py: the Minecraft versions a release note names.

Plain unittest, so the Linux check can run it without pytest.
"""

import io
import json
import sys
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "automation"))

import release_note  # noqa: E402

FORMATS = {88: "26.2", 97: "26.3"}


class FormatRange(unittest.TestCase):
    def test_reads_min_and_max_format(self):
        self.assertEqual(release_note.format_range({"min_format": 88, "max_format": 97}), (88, 97))

    def test_reads_the_major_part_of_a_major_minor_format(self):
        pack = {"min_format": [88, 0], "max_format": [97, 1]}
        self.assertEqual(release_note.format_range(pack), (88, 97))

    def test_min_and_max_format_win_over_the_older_keys(self):
        pack = {"pack_format": 15, "supported_formats": [15, 34], "min_format": 88, "max_format": 97}
        self.assertEqual(release_note.format_range(pack), (88, 97))

    def test_reads_supported_formats_as_a_list(self):
        pack = {"pack_format": 15, "supported_formats": [15, 255]}
        self.assertEqual(release_note.format_range(pack), (15, 255))

    def test_reads_supported_formats_as_an_object(self):
        pack = {"supported_formats": {"min_inclusive": 88, "max_inclusive": 97}}
        self.assertEqual(release_note.format_range(pack), (88, 97))

    def test_reads_supported_formats_as_a_single_number(self):
        self.assertEqual(release_note.format_range({"supported_formats": 88}), (88, 88))

    def test_falls_back_to_pack_format(self):
        self.assertEqual(release_note.format_range({"pack_format": 88}), (88, 88))

    def test_refuses_a_pack_with_no_format(self):
        with self.assertRaises(release_note.ReleaseNoteError):
            release_note.format_range({"description": "no format"})

    def test_refuses_a_format_that_is_not_a_whole_number(self):
        with self.assertRaises(release_note.ReleaseNoteError):
            release_note.format_range({"pack_format": "88"})

    def test_refuses_a_range_that_runs_backwards(self):
        with self.assertRaises(release_note.ReleaseNoteError):
            release_note.format_range({"supported_formats": [97, 88]})


class VersionsIn(unittest.TestCase):
    def test_lists_the_known_versions_inside_the_range(self):
        self.assertEqual(release_note.versions_in(88, 97, FORMATS), ["26.2", "26.3"])

    def test_a_single_format(self):
        self.assertEqual(release_note.versions_in(88, 88, FORMATS), ["26.2"])

    def test_a_wide_range_names_only_what_the_map_knows(self):
        # RP-Human's pack.mcmeta declares 15-255
        self.assertEqual(release_note.versions_in(15, 255, FORMATS), ["26.2", "26.3"])

    def test_a_range_with_no_known_format(self):
        self.assertEqual(release_note.versions_in(90, 96, FORMATS), [])

    def test_oldest_first_whatever_the_order_of_the_map(self):
        self.assertEqual(release_note.versions_in(88, 97, {97: "26.3", 88: "26.2"}), ["26.2", "26.3"])


class Note(unittest.TestCase):
    def test_two_versions(self):
        self.assertEqual(
            release_note.note("v4.1.3", [(88, 97)], FORMATS),
            ("Version v4.1.3 for Minecraft 26.2 and 26.3", []),
        )

    def test_one_version(self):
        self.assertEqual(
            release_note.note("v4.1.3", [(88, 88)], FORMATS),
            ("Version v4.1.3 for Minecraft 26.2", []),
        )

    def test_three_versions(self):
        formats = {88: "26.2", 97: "26.3", 101: "26.4"}
        self.assertEqual(
            release_note.note("v5", [(88, 101)], formats)[0],
            "Version v5 for Minecraft 26.2, 26.3 and 26.4",
        )

    def test_a_range_with_no_known_format_is_named_by_its_numbers(self):
        self.assertEqual(release_note.note("v4.1.3", [(90, 96)], FORMATS)[0], "Version v4.1.3 for pack format 90-96")
        self.assertEqual(release_note.note("v4.1.3", [(99, 99)], FORMATS)[0], "Version v4.1.3 for pack format 99")

    def test_zips_that_agree_do_not_warn(self):
        self.assertEqual(
            release_note.note("v4.1.3", [(88, 97)] * 4, FORMATS),
            ("Version v4.1.3 for Minecraft 26.2 and 26.3", []),
        )

    def test_ranges_that_name_the_same_versions_do_not_warn(self):
        # A Sodium release: the Sodium zips declare 15-255, the zips converted from them 88-97
        ranges = [(15, 255), (15, 255), (88, 97), (88, 97), (88, 97), (88, 97)]
        self.assertEqual(
            release_note.note("v4.1.3", ranges, FORMATS),
            ("Version v4.1.3 for Minecraft 26.2 and 26.3", []),
        )

    def test_names_only_what_every_zip_supports_and_warns_once(self):
        text, warnings = release_note.note("v4.1.3", [(88, 97), (88, 97), (88, 88)], FORMATS)
        self.assertEqual(text, "Version v4.1.3 for Minecraft 26.2")
        self.assertEqual(len(warnings), 1)
        self.assertIn("different Minecraft versions (pack formats 88, 88-97)", warnings[0])

    def test_zips_with_nothing_in_common_name_no_version(self):
        text, warnings = release_note.note("v4.1.3", [(88, 88), (97, 97)], FORMATS)
        self.assertEqual(text, "Version v4.1.3")
        self.assertEqual(len(warnings), 1)
        self.assertIn("no pack format is supported by every zip (88, 97)", warnings[0])


def make_zip(folder, name, mcmeta, member="pack.mcmeta", bom=False):
    """A zip holding mcmeta as its pack.mcmeta, plus one asset."""
    path = Path(folder) / name
    data = json.dumps(mcmeta).encode("utf-8")
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(member, (b"\xef\xbb\xbf" if bom else b"") + data)
        archive.writestr("assets/minecraft/textures/block/stone.png", b"png")
    return path


class ReadPack(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_reads_the_pack_section_at_the_root(self):
        archive = make_zip(self.tmp.name, "a.zip", {"pack": {"pack_format": 88, "description": "x"}})
        self.assertEqual(release_note.read_pack(archive)["pack_format"], 88)

    def test_reads_a_file_that_starts_with_a_byte_order_mark(self):
        archive = make_zip(self.tmp.name, "a.zip", {"pack": {"pack_format": 88}}, bom=True)
        self.assertEqual(release_note.read_pack(archive)["pack_format"], 88)

    def test_finds_a_pack_mcmeta_one_folder_down(self):
        archive = make_zip(self.tmp.name, "a.zip", {"pack": {"pack_format": 97}}, member="Human/pack.mcmeta")
        self.assertEqual(release_note.read_pack(archive)["pack_format"], 97)

    def test_refuses_a_zip_without_pack_mcmeta(self):
        archive = Path(self.tmp.name) / "empty.zip"
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("readme.txt", "hi")
        with self.assertRaises(release_note.ReleaseNoteError):
            release_note.read_pack(archive)

    def test_refuses_a_file_that_is_not_a_zip(self):
        bad = Path(self.tmp.name) / "bad.zip"
        bad.write_bytes(b"not a zip")
        with self.assertRaises(release_note.ReleaseNoteError):
            release_note.read_pack(bad)


class CommandLine(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def run_main(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = release_note.main(list(args))
        return code, out.getvalue(), err.getvalue()

    def test_prints_the_note_using_the_real_map(self):
        # RP-Human's own Sodium declaration, and a Vanilla zip from the shader base
        sodium = make_zip(
            self.tmp.name,
            "Human-Sodium.zip",
            {"pack": {"pack_format": 15, "supported_formats": [15, 255], "min_format": 15, "max_format": 255}},
        )
        vanilla = make_zip(self.tmp.name, "Human-Vanilla.zip", {"pack": {"min_format": 88, "max_format": 97}})
        code, out, err = self.run_main("v4.1.3", str(sodium), str(vanilla))
        # No warning: both ranges name 26.2 and 26.3
        self.assertEqual((code, out, err), (0, "Version v4.1.3 for Minecraft 26.2 and 26.3\n", ""))

    def test_warnings_go_to_stderr(self):
        a = make_zip(self.tmp.name, "a.zip", {"pack": {"min_format": 88, "max_format": 97}})
        b = make_zip(self.tmp.name, "b.zip", {"pack": {"pack_format": 88}})
        code, out, err = self.run_main("v1", str(a), str(b))
        self.assertEqual((code, out), (0, "Version v1 for Minecraft 26.2\n"))
        self.assertIn("warning", err)

    def test_usage_without_a_zip(self):
        code, out, err = self.run_main("v1")
        self.assertEqual(code, 2)
        self.assertIn("usage", err)

    def test_an_unreadable_zip_fails_with_its_name(self):
        code, out, err = self.run_main("v1", str(Path(self.tmp.name) / "missing.zip"))
        self.assertEqual((code, out), (1, ""))
        self.assertIn("missing.zip", err)


if __name__ == "__main__":
    unittest.main()
