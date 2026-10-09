"""Add the shader base to a pack that isn't built by generateVanilla.py.

The Sodium pack is the pack repository as it is, so the release adds the base
to its copy before zipping it:

    python applyShaderBase.py <pack folder> [<output folder>]

The output defaults to the pack folder itself, so run it on a copy: it also
signs the fluid textures there. A pack whose repository syncShaderBase.py keeps
up to date has the base already; this only brings it up to the newest. Exits non-zero if the pack ships a file the
base owns, or if any shader import then still doesn't resolve.
"""

import argparse
import sys
from pathlib import Path

import shader_base

parser = argparse.ArgumentParser(description="Add the MCME shader base to a pack.")
parser.add_argument("pack_path", help="The pack, with its assets/ folder.")
parser.add_argument(
    "output_path", nargs="?", help="Where to add the base. Defaults to the pack."
)
args = parser.parse_args()

pack_path = Path(args.pack_path)
output_path = Path(args.output_path) if args.output_path else pack_path

try:
    config = shader_base.apply([pack_path], output_path)
    shader_base.finish(output_path, config)
except shader_base.ShaderBaseError as e:
    sys.exit(f"ERROR: {e}")
print(f"Shader base added to {output_path}")
