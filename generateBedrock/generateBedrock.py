"""Convert a Java resource pack into a Bedrock resource pack and Geyser block mappings.

    python generateBedrock/generateBedrock.py <pack> <output folder> <vanilla resources> --name <Pack>

The output folder becomes the Bedrock pack (manifest.json at its top); the
mappings go to --mappings, for Geyser's custom_mappings folder. docs/bedrock.md
says how the conversion works, what it can't carry over, and how to put the
result on a Geyser server.

A problem with one model or texture prints a WARNING!!! line and skips it, as
generateVanilla does. Exit status: 0 converted (or turned off by the pack's
.mcme-bedrock.json, which writes nothing); 1 the run couldn't start.
"""

import argparse
import json
import sys
from pathlib import Path

import bedrock_pack
import bedrock_settings
import convert
import geometry

HERE = Path(__file__).resolve().parent


def main(argv=None):
    parser = argparse.ArgumentParser(description="Convert a Java resource pack for Bedrock players on Geyser.")
    parser.add_argument("input_path", help="The Java pack: for a Sodium pack, its Sodium variant")
    parser.add_argument("output_path", help="Folder to write the Bedrock pack in; use a new, empty one")
    parser.add_argument("vanilla_path", help="The vanilla client resources (the folder that holds assets/)")
    parser.add_argument("--name", required=True, help="The pack's name in the automation, like Human: its UUIDs and block names come from it")
    parser.add_argument("--tag", help="The release tag, like v4.1.3: the Bedrock pack's version")
    parser.add_argument("--mappings", help="File to write Geyser's block mappings to. Default: <output>-geyser.json")
    parser.add_argument("--mcpack", help="Also zip the pack into this .mcpack file")
    parser.add_argument("--geometry", choices=geometry.MODES, help="Override the pack's setting: hybrid, polymesh or cubes")
    parser.add_argument("--tint", choices=bedrock_settings.TINTS, help="Override the pack's setting: biome or baked")
    parser.add_argument("--blocks", default=str(HERE / "java_blocks.json"), help="The Java block list (tools/DumpBlockStates.java)")
    parser.add_argument("--debug", action="store_true", help="Print each block as it is converted")
    args = parser.parse_args(argv)

    pack, output, vanilla = Path(args.input_path), Path(args.output_path), Path(args.vanilla_path)
    print(f"Bedrock source: {pack}")
    print(f"Bedrock output: {output}")
    if not (pack / "assets").is_dir():
        print(f"ERROR: {pack} has no assets folder, so there's nothing to convert.", file=sys.stderr)
        return 1
    if not (vanilla / "assets" / "minecraft" / "blockstates").is_dir():
        print(f"ERROR: {vanilla} has no assets/minecraft/blockstates, so the vanilla blocks can't be read.", file=sys.stderr)
        return 1

    warned = set()

    def warn(message):
        # In a release, the Bedrock step's warnings follow the Java steps': say whose they are
        if not message.startswith("Bedrock: "):
            message = f"Bedrock: {message}"
        if message not in warned:
            warned.add(message)
            print(f"WARNING!!! {message}", flush=True)

    def debug(message):
        if args.debug:
            print(message, flush=True)

    settings = bedrock_settings.load(pack, warn)
    if args.geometry:
        settings.geometry = args.geometry
    if args.tint:
        settings.tint = args.tint
    if not settings.enabled:
        print(f"The Bedrock conversion is turned off for this pack ({bedrock_settings.FILE_NAME}), so no Bedrock pack is made.")
        return 0

    name = settings.name or f"MCME {args.name}"
    converter = convert.Converter(pack, vanilla, settings, args.name, Path(args.blocks), warn, debug).run()
    description = bedrock_pack.java_description(pack) or name
    if args.tag:
        description = f"{description} ({args.tag}, converted for Bedrock)"
    version = bedrock_pack.version_from_tag(args.tag)

    output.mkdir(parents=True, exist_ok=True)
    bedrock_pack.write_manifest(output, args.name, name, description, version)
    bedrock_pack.copy_icon(pack, output)
    converter.write(output, name)
    mappings = Path(args.mappings) if args.mappings else output.with_name(output.name + "-geyser.json")
    mappings.parent.mkdir(parents=True, exist_ok=True)
    with open(mappings, "w", encoding="utf-8", newline="\n") as f:
        json.dump(converter.mappings_file(), f, indent=1)
        f.write("\n")
    if args.mcpack:
        bedrock_pack.zip_pack(output, Path(args.mcpack))

    report = converter.report
    for kind, text in convert.summary_lines(report):
        print(f"WARNING!!! {text}" if kind == "warning" else text, flush=True)
    print(f"Bedrock pack {name} {'.'.join(map(str, version))} for Minecraft {report.minecraft}'s blocks; "
          f"{converter.textures.count()} texture(s); Geyser mappings: {mappings}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
