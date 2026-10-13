"""Do two zips hold the same files? It compares what is in them, not the zip files' bytes.

7-Zip stores each file's modification time, so zips of the same files made
from separate copies differ byte for byte. The release scripts use this to
check that variants which should differ do:

    python3 zips.py same <a.zip> <b.zip>

exits 0 when both hold the same files with the same contents, 1 when they
differ, and 2 when it can't tell: a zip can't be read (the reason goes to
stderr, starting "zips:"), or the usage is wrong. Folder entries don't count,
since a zip may list its folders or not.
"""

import sys
import zipfile


def contents(path):
    """{name: (CRC-32, size)} of every file in the zip at path."""
    with zipfile.ZipFile(path) as archive:
        return {info.filename: (info.CRC, info.file_size) for info in archive.infolist() if not info.is_dir()}


def same_contents(a, b):
    """True when the zips at a and b hold the same files with the same contents."""
    return contents(a) == contents(b)


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 3 or args[0] != "same":
        print("usage: zips.py same <a.zip> <b.zip>", file=sys.stderr)
        return 2
    try:
        return 0 if same_contents(args[1], args[2]) else 1
    except Exception as e:  # noqa: BLE001 - any failure is "can't tell": 1 would mean "they differ"
        print(f"zips: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
