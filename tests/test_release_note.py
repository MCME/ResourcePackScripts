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
        self.assertEqual(release_note.note("v4.1.3", [(90, 96)], FORMATS)[0], "Version v4.1.3 for pack format 90–96")
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
        self.assertIn("different Minecraft versions (pack formats 88, 88–97)", warnings[0])

    def test_zips_with_nothing_in_common_name_no_version(self):
        text, warnings = release_note.note("v4.1.3", [(88, 88), (97, 97)], FORMATS)
        self.assertEqual(text, "Version v4.1.3")
        self.assertEqual(len(warnings), 1)
        self.assertIn("no pack format is supported by every zip (88, 97)", warnings[0])


if __name__ == "__main__":
    unittest.main()
