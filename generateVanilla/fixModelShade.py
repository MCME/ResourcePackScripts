"""Keep a pack's unshaded model elements unshaded on 26.3 (model_shade, docs/conversion.md).

    python fixModelShade.py <pack> [<pack> ...] [--check]

Adds "shade_direction_override": "up" next to every "shade": false: 26.3
reads only the new key, 26.2 only the old one. --check changes nothing and
fails when an element lacks it, as CI wants.
"""

import argparse
import sys

import model_shade

parser = argparse.ArgumentParser(description='Add "shade_direction_override" to a pack\'s "shade": false elements.')
parser.add_argument("pack_paths", nargs="+", help="The pack, with its assets/ folder.")
parser.add_argument("--check", action="store_true", help="Change nothing; fail when an element lacks the override.")
args = parser.parse_args()

failed = False
for pack_path in args.pack_paths:
    try:
        found = model_shade.check(pack_path) if args.check else model_shade.fix(pack_path)
    except model_shade.ModelShadeError as e:
        sys.exit(f"ERROR: {e}")
    for path, count in found.items():
        print(f"{path}: {count} element(s) {'lack' if args.check else 'given'} {model_shade.OVERRIDE_KEY}")
    elements = sum(found.values())
    if args.check:
        failed = failed or bool(found)
        print(f"{pack_path}: {elements} element(s) in {len(found)} model(s) lack {model_shade.OVERRIDE_KEY}")
    else:
        print(f"{pack_path}: {elements} element(s) in {len(found)} model(s) fixed")

if failed:
    sys.exit(f"ERROR: run fixModelShade.py on the pack: 26.3 shades these elements darker")
