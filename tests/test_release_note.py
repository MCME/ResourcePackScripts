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


if __name__ == "__main__":
    unittest.main()
