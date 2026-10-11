"""Tests for automation/zips.py: do two zips hold the same files?

Plain unittest, so WSL can run it without pytest.
"""

import io
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "automation"))

import zips  # noqa: E402

FILES = {
    "pack.mcmeta": b'{"pack": {"pack_format": 88}}',
    "assets/minecraft/textures/block/stone.png": b"stone",
}


class ZipsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def make(self, name, files, date_time=(2026, 10, 10, 12, 0, 0), compression=zipfile.ZIP_DEFLATED):
        """A zip holding files ({name: bytes}; a name ending in / is a folder entry)."""
        path = self.tmp / name
        with zipfile.ZipFile(path, "w") as archive:
            for member, data in files.items():
                archive.writestr(zipfile.ZipInfo(member, date_time=date_time), data, compress_type=compression)
        return path


class SameContents(ZipsTest):
    def test_the_same_files_are_the_same(self):
        self.assertTrue(zips.same_contents(self.make("a.zip", FILES), self.make("b.zip", FILES)))

    def test_ignores_when_the_files_were_made(self):
        # What 7-Zip does to two zips of the same files made from separate copies
        a = self.make("a.zip", FILES, date_time=(2026, 10, 10, 12, 0, 0))
        b = self.make("b.zip", FILES, date_time=(2026, 10, 10, 12, 5, 0))
        self.assertNotEqual(a.read_bytes(), b.read_bytes())
        self.assertTrue(zips.same_contents(a, b))

    def test_ignores_how_the_files_were_compressed(self):
        a = self.make("a.zip", FILES, compression=zipfile.ZIP_STORED)
        b = self.make("b.zip", FILES, compression=zipfile.ZIP_DEFLATED)
        self.assertTrue(zips.same_contents(a, b))

    def test_ignores_the_order_of_the_files(self):
        backwards = dict(reversed(list(FILES.items())))
        self.assertTrue(zips.same_contents(self.make("a.zip", FILES), self.make("b.zip", backwards)))

    def test_ignores_folder_entries(self):
        with_folders = {"assets/": b"", "assets/minecraft/": b"", **FILES}
        self.assertTrue(zips.same_contents(self.make("a.zip", FILES), self.make("b.zip", with_folders)))

    def test_a_changed_file_differs(self):
        changed = dict(FILES, **{"assets/minecraft/textures/block/stone.png": b"footprints"})
        self.assertFalse(zips.same_contents(self.make("a.zip", FILES), self.make("b.zip", changed)))

    def test_an_added_file_differs(self):
        added = dict(FILES, **{"assets/minecraft/textures/block/activator_rail.png": b"footprints"})
        self.assertFalse(zips.same_contents(self.make("a.zip", FILES), self.make("b.zip", added)))

    def test_a_renamed_file_differs(self):
        renamed = {"pack.mcmeta": FILES["pack.mcmeta"], "assets/minecraft/textures/block/dirt.png": b"stone"}
        self.assertFalse(zips.same_contents(self.make("a.zip", FILES), self.make("b.zip", renamed)))


class CommandLine(ZipsTest):
    def run_main(self, *args):
        err = io.StringIO()
        with redirect_stderr(err):
            code = zips.main([str(arg) for arg in args])
        return code, err.getvalue()

    def test_exits_0_for_the_same_files(self):
        self.assertEqual(self.run_main("same", self.make("a.zip", FILES), self.make("b.zip", FILES))[0], 0)

    def test_exits_1_for_different_files(self):
        changed = dict(FILES, **{"pack.mcmeta": b"{}"})
        self.assertEqual(self.run_main("same", self.make("a.zip", FILES), self.make("b.zip", changed))[0], 1)

    def test_exits_2_when_a_zip_is_missing(self):
        code, err = self.run_main("same", self.make("a.zip", FILES), self.tmp / "gone.zip")
        self.assertEqual(code, 2)
        self.assertIn("zips:", err)

    def test_exits_2_for_a_file_that_is_not_a_zip(self):
        not_a_zip = self.tmp / "b.zip"
        not_a_zip.write_bytes(b"not a zip")
        code, err = self.run_main("same", self.make("a.zip", FILES), not_a_zip)
        self.assertEqual(code, 2)
        self.assertIn("zips:", err)

    def test_exits_2_when_it_fails_unexpectedly(self):
        # 1 would read as "they differ", and a Footprints check would let a broken zip through
        with mock.patch.object(zips, "contents", side_effect=RuntimeError("boom")):
            code, err = self.run_main("same", self.make("a.zip", FILES), self.make("b.zip", FILES))
        self.assertEqual(code, 2)
        self.assertIn("zips: boom", err)

    def test_exits_2_on_wrong_usage(self):
        for args in ((), ("same", "a.zip"), ("differ", "a.zip", "b.zip")):
            with self.subTest(args=args):
                self.assertEqual(self.run_main(*args)[0], 2)

    def test_runs_as_a_script(self):
        # How the release scripts call it
        a, b = self.make("a.zip", FILES), self.make("b.zip", FILES)
        script = REPO_ROOT / "automation" / "zips.py"
        self.assertEqual(subprocess.run([sys.executable, str(script), "same", str(a), str(b)]).returncode, 0)


if __name__ == "__main__":
    unittest.main()
