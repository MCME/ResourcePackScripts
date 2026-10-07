"""Check a pack's shaders before players get them (shader_check, docs/shader-base.md).

    python checkShaders.py <pack> [--glslang PATH] [--fetch tested|latest] [--jar PATH ...]

It always checks the rules (#version, #extension). With the game's and the
mods' jars - the ones installed in .minecraft, or downloaded with --fetch - it
checks the pack's Distant Horizons shaders against DH's own, and with glslang
(--glslang, $GLSLANG or on the PATH) and moderngl it compiles every shader
the pack has. --require-compiler fails when it couldn't compile, as CI wants.

--fetch tested takes the versions the shaders were tested on
(shader_versions.json); --fetch latest the newest of each mod for that
Minecraft version, and says which are newer than the tested ones.
"""

import argparse
import os
import sys
from pathlib import Path

import shader_check

parser = argparse.ArgumentParser(description="Check a pack's shaders.")
parser.add_argument("pack_path", help="The pack, with its assets/ folder.")
parser.add_argument("--glslang", help="glslang's executable.")
parser.add_argument("--jar", action="append", default=[], help="The game's or a mod's jar, in place of the installed one.")
parser.add_argument("--fetch", choices=("tested", "latest"), help="Download the jars instead of using the installed ones.")
parser.add_argument("--cache", default=str(Path.home() / ".cache" / "mcme-shaders"), help="Where --fetch keeps them.")
parser.add_argument("--no-driver", action="store_true", help="Don't link on an OpenGL driver even with moderngl.")
parser.add_argument("--require-compiler", action="store_true", help="Fail when glslang isn't there.")
parser.add_argument("--verbose", action="store_true", help="List every program that passed.")
args = parser.parse_args()

github = os.environ.get("GITHUB_ACTIONS") == "true"
tested = shader_check.tested_versions()
versions = dict(tested)

if args.fetch == "latest":
    latest = shader_check.latest_versions(tested["minecraft"])
    for jar_id, version in latest.items():
        if version != tested.get(jar_id):
            message = (f"{shader_check.NAMES[jar_id]} {version} is out; the shaders were tested on {tested.get(jar_id)}"
                       + (" - checked against it below" if jar_id in ("sodium", "distanthorizons") else ""))
            print(f"::notice::{message}" if github else f"NOTICE: {message}")
            if jar_id != "minecraft":
                versions[jar_id] = version

jars = shader_check.fetch_jars(versions, Path(args.cache)) if args.fetch else shader_check.find_jars(tested["minecraft"])
for path in args.jar:
    jar_id = shader_check._jar_id(Path(path))
    if jar_id:
        jars[jar_id] = Path(path)
for jar_id in shader_check.JAR_IDS:
    if jar_id in jars:
        print(f"{shader_check.NAMES[jar_id]} {shader_check.jar_version(jars[jar_id])}: {jars[jar_id]}")
    else:
        print(f"{shader_check.NAMES[jar_id]}: no jar, so what needs it isn't checked")

glslang = shader_check.find_glslang(args.glslang)
context = None if args.no_driver else shader_check.driver_context()
print(f"glslang: {glslang or 'not found'}")
print(f"OpenGL: {context.info['GL_RENDERER'] + ' ' + context.info['GL_VERSION'] if context else 'none'}")

report = shader_check.check(args.pack_path, jars, glslang, context)
if args.verbose:
    print("\n".join(report.notes))
if not glslang and args.require_compiler:
    report.problems.append("glslang wasn't found, so nothing was compiled")

if report.problems:
    for problem in report.problems:
        if github:
            print(f"::error::{problem.splitlines()[0]}")
        print(f"PROBLEM {problem}")
    sys.exit(f"{len(report.problems)} problem(s) in {args.pack_path}'s shaders.")
print(f"{args.pack_path}: shaders OK ({len(report.notes)} programs compiled)" if glslang or context
      else f"{args.pack_path}: rules OK (nothing compiled)")
