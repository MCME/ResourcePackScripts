"""Write the fluids' codes into a pack's textures (see fluid_signature.py).

The build signs every pack's water itself. A pack's own fluids, such as RP-
Mordor's lava and ice, are signed in its repository, after every edit of the
textures:

    python signFluids.py <pack folder> lava
    python signFluids.py <pack folder> lava --check
"""

import argparse
import sys

import fluid_signature

GROUPS = {
    "lava": fluid_signature.LAVA,
    "water": fluid_signature.WATER,
    "ice": fluid_signature.ICE,
    "all": tuple(fluid_signature.KINDS),
}

parser = argparse.ArgumentParser(description="Sign a pack's fluid textures for the terrain shaders.")
parser.add_argument("pack_path", help="The pack, with its assets/ folder.")
parser.add_argument("fluids", choices=GROUPS, help="Which textures to sign.")
parser.add_argument("--check", action="store_true", help="Only report whether they carry their codes.")
args = parser.parse_args()

messages, ok = fluid_signature.sign_pack(args.pack_path, GROUPS[args.fluids], args.check)
print("\n".join(messages) or "No such textures in the pack.")
sys.exit(0 if ok else 1)
