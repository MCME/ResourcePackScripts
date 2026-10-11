"""The pack format map in generateVanilla/pack_formats.json.

Plain unittest, so the Linux check can run it without pytest.
"""

import json
import unittest
from pathlib import Path

FORMATS_PATH = Path(__file__).resolve().parent.parent / "generateVanilla" / "pack_formats.json"


def _refuse_repeated_keys(pairs):
    # json.load keeps the last of two equal keys, which would hide an editing slip
    formats = dict(pairs)
    if len(formats) != len(pairs):
        raise ValueError(f"{FORMATS_PATH.name} lists a pack format twice")
    return formats


def load():
    with open(FORMATS_PATH, encoding="utf-8") as f:
        return json.load(f, object_pairs_hook=_refuse_repeated_keys)


class PackFormatMap(unittest.TestCase):
    def test_maps_whole_numbers_to_minecraft_versions(self):
        for pack_format, version in load().items():
            # No leading zero: read as a number, "088" would be a second 88
            self.assertRegex(pack_format, r"^[1-9]\d*\Z")
            self.assertRegex(version, r"^\d+\.\d+(\.\d+)?\Z")

    def test_versions_are_unique_and_rise_with_the_format(self):
        formats = load()
        versions = [formats[key] for key in sorted(formats, key=int)]
        as_numbers = [tuple(int(part) for part in version.split(".")) for version in versions]
        # Compared as numbers, so "26.03" counts as a repeat of "26.3"
        self.assertEqual(len(as_numbers), len(set(as_numbers)))
        self.assertEqual(as_numbers, sorted(as_numbers))

    def test_knows_the_two_versions_the_network_serves(self):
        # The same two formats as shader_base.py's OLDEST_FORMAT and OVERLAY_FORMAT
        formats = load()
        self.assertEqual(formats["88"], "26.2")
        self.assertEqual(formats["97"], "26.3")


if __name__ == "__main__":
    unittest.main()
