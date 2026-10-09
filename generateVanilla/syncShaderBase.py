"""Write the shader base into a pack's repository (docs/shader-base.md).

The release scripts on the server zip a pack's repository as it is, so the
base has to be in it - every file of it, and the modules the pack turns on in
its .mcme-shaders.json:

    python syncShaderBase.py <pack repository> [--force]

It writes them, keeps the pack's hooks and its own files, deletes what an
earlier sync wrote that the pack no longer gets (a module turned off), signs
the pack's water, its modules' and its own fluid textures, and records what it
wrote in .mcme-shaders.lock. Commit all of it.

It refuses a pack whose copies of base files were changed by hand, as the
build does. --force overwrites them: for a pack's first sync, over the copies
it kept before - check first that it had no changes of its own in them.
"""

import argparse
import sys

import shader_base

parser = argparse.ArgumentParser(description="Write the MCME shader base into a pack repository.")
parser.add_argument("pack_path", help="The pack repository, with its assets/ folder.")
parser.add_argument("--force", action="store_true", help="Overwrite copies changed by hand.")
args = parser.parse_args()

try:
    done = shader_base.sync(args.pack_path, args.force)
except shader_base.ShaderBaseError as e:
    sys.exit(f"ERROR: {e}")
print("\n".join(done) or "Already up to date.")
