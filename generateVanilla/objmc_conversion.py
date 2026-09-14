"""Converting an mcme sodium model into a vanilla shader model, via objmc.

objmc is an external script. It reads an `.obj` plus a texture and emits a
vanilla model JSON whose geometry is baked into an accompanying PNG - the model
JSON itself is a near-fixed shell, so almost everything objmc decides ends up in
the texture rather than in the JSON.

The conversion runs in three stages, and only the middle one knows anything
about objmc:

1. `_plan_conversion` - read the model JSON, the `.objmeta` and the `.mtl`, and
   settle every path and setting the conversion needs. Pure reading; knows
   nothing about objmc beyond the fact that `options` are flag names.
2. `_run_objmc` - build the argv and run it. **This is objmc's CLI surface.**
3. `_reshape_output` and `_apply_parent` - take the model JSON objmc produced,
   fix it into our pack's conventions and link up parents. `_reshape_output`
   is **objmc's output format**; `_apply_parent` is purely our own.

That split is what makes an objmc upgrade tractable: a change lands in stage 2
or stage 3, and which one it lands in tells you whether objmc's CLI moved or
its output did. Stages 1 and the parent linking should not need to move at all.

The golden tests in tests/test_objmc_golden.py pin stage 2 and 3 against a real
objmc. Everything else is covered by the faked-subprocess tests.
"""

import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import constants
import rotate_obj
import util
import yaml

# model_path -> the output file it was written to, or PARENT_DONE_VALUE once a
# shared parent has been extracted for it. Module-level because a model can be
# reached from more than one traversal root, and the second visit is what
# triggers parent extraction.
converted_models = {}


# The suffix identifying a rotated variant of a model. Shared by the rotated
# .obj, the converted model and its texture, so they all have to agree.
def rotation_suffix(rotation: tuple[str, float] | None):
    if rotation is None:
        return ""
    axis, angle = rotation
    return f"_{axis}_{angle}"


@dataclass
class ConversionPlan:
    """Everything the conversion needs, settled before objmc is involved."""

    model_path: str
    rotation: tuple[str, float] | None
    suffix: str
    # The .obj objmc reads. For a rotated model this is a temporary file written
    # by rotate_obj and deleted afterwards; otherwise it is source_obj_file.
    obj_file: Path
    source_obj_file: Path
    texture_file: Path
    output_model_file: Path
    output_texture_file: Path
    output_texture_path: str
    offset: list = field(default_factory=lambda: ["-0.5", "0.0", "-0.5"])
    visibility: int = 7
    options: list = field(default_factory=list)
    manual_parent_model: str | None = None
    omnidirectional_parent: bool = False


# --------------------------------------------------------------------------
# Stage 1: work out what to convert
# --------------------------------------------------------------------------


def _resolve_obj_and_mtl(model_file: Path, model_path: str):
    """The .obj and .mtl this model names, as pack-relative paths without suffix.

    Returns None when the model names no .obj at all, which is the caller's
    signal that there is nothing to convert.
    """
    mtl_path = model_path
    obj_model_path = model_path

    with open(model_file, "r", encoding="utf-8-sig") as f:
        data = json.load(f)

    if "model" not in data:
        return None

    namespace, model_ref = util.split_namespaced(
        data["model"],
        constants.MCME_NAMESPACE,  # Q: Why is MCME the default here?
    )
    if namespace == constants.MCME_NAMESPACE:
        obj_model_path = model_ref
    else:
        print(f"Unexpected namespace: {namespace} in mcme model file.", flush=True)
    obj_model_path = obj_model_path.removeprefix("models/").removesuffix(
        constants.OBJ_MODEL_EXTENSION
    )

    if "mtl_override" in data:
        namespace, mtl_ref = util.split_namespaced(
            data["mtl_override"], constants.MCME_NAMESPACE
        )
        if namespace == constants.MCME_NAMESPACE:
            mtl_path = mtl_ref
        else:
            print(f"Unexpected namespace: {namespace} in mcme mtl file.", flush=True)
    mtl_path = mtl_path.removeprefix("models/").removesuffix(constants.MTL_EXTENSION)

    return obj_model_path, mtl_path


def _read_objmeta(meta_file: Path, model_path: str) -> dict:
    """The .objmeta settings, or the defaults when there is no such file."""
    settings = {
        "texture_path": None,
        "output_texture_path": None,
        "offset": ["-0.5", "0.0", "-0.5"],
        "options": [],
        "visibility": 7,
        "manual_parent_model": None,
        "omnidirectional_parent": False,
    }
    if not os.path.exists(meta_file):
        return settings

    try:
        with open(meta_file, "r", encoding="utf-8-sig") as f:
            meta_data = yaml.safe_load(f)

        settings["texture_path"] = meta_data.get("texture", None)
        settings["output_texture_path"] = meta_data.get("output_texture", None)
        settings["offset"] = meta_data.get("offset", "-0.5 0.0 -0.5").split()
        settings["options"] = meta_data.get("options", [])
        settings["visibility"] = meta_data.get("visibility", 7)
        # NOTE: raises AttributeError when the file has no `parent` key. Latent
        # only because all 1246 .objmeta files in RP-Human happen to set one.
        settings["manual_parent_model"] = (
            meta_data.get("parent", None).split(":")[-1].strip()
        )
        settings["omnidirectional_parent"] = meta_data.get(
            "omnidirectional_parent", False
        )
    except FileNotFoundError:
        print(f"Meta file not found for {model_path})")
    except yaml.YAMLError as exc:
        print(f"Error parsing objmeta file for {model_path}: {exc}")

    return settings


def _texture_from_mtl(mtl_file: Path):
    """The texture the .mtl names, or None if the file has no map_Kd line."""
    with open(mtl_file, "r", encoding="utf-8-sig") as f:
        for mtl_line in f:
            if mtl_line.startswith("map_Kd"):
                return mtl_line.split()[1].strip()
    return None


def _plan_conversion(
    input_path, output_path, model_path, rotation
) -> ConversionPlan | None:
    """Settle every path and setting. None means there is nothing to convert."""
    sodium_models = input_path / constants.RELATIVE_SODIUM_MODELS_PATH

    model_file = sodium_models / Path(model_path + constants.VANILLA_MODEL_EXTENSION)
    if not model_file.exists():
        print(
            "        WARNING! Expected model file not found: " + str(model_file),
            flush=True,
        )
        return None

    resolved = _resolve_obj_and_mtl(model_file, model_path)
    if resolved is None:
        return None
    obj_model_path, mtl_path = resolved

    source_obj_file = sodium_models / Path(
        obj_model_path + constants.OBJ_MODEL_EXTENSION
    )
    if not os.path.exists(source_obj_file):
        return None

    meta = _read_objmeta(
        sodium_models / Path(model_path + constants.OBJMETA_EXTENSION), model_path
    )

    texture_path = meta["texture_path"]
    if not texture_path:
        mtl_file = sodium_models / Path(mtl_path + constants.MTL_EXTENSION)
        if not mtl_file.exists():
            print(f"Missing .mtl file {mtl_file}.")
            return None
        texture_path = _texture_from_mtl(mtl_file)

    if not texture_path:
        print(f"        Missing texture for {model_path}", flush=True)
        return None

    relative_texture_path = constants.RELATIVE_SODIUM_TEXTURES_PATH
    namespace, texture_path = util.split_namespaced(
        texture_path, constants.MCME_NAMESPACE
    )
    if namespace == constants.VANILLA_NAMESPACE:
        relative_texture_path = constants.RELATIVE_VANILLA_TEXTURES_PATH
    elif namespace != constants.MCME_NAMESPACE:
        print(
            "WARNING!!! Unexpected texture namespace: "
            + namespace
            + "for "
            + texture_path,
            flush=True,
        )

    output_texture_path = meta["output_texture_path"]
    if not output_texture_path:
        # The output texture carries baked voxel data, so it is named after the
        # model rather than the texture - several models may share one sodium
        # texture but each needs its own baked output.
        output_texture_path = model_path

    # An unrotated model has an empty suffix, so these paths are the same either
    # way - only the .obj objmc reads from differs.
    suffix = rotation_suffix(rotation)

    return ConversionPlan(
        model_path=model_path,
        rotation=rotation,
        suffix=suffix,
        obj_file=sodium_models
        / Path(obj_model_path + suffix + constants.OBJ_MODEL_EXTENSION),
        source_obj_file=source_obj_file,
        texture_file=input_path
        / relative_texture_path
        / Path(texture_path + constants.TEXTURE_EXTENSION),
        output_model_file=output_path
        / constants.RELATIVE_SODIUM_MODELS_PATH
        / Path(model_path + suffix + constants.VANILLA_MODEL_EXTENSION),
        output_texture_file=output_path
        / constants.RELATIVE_SODIUM_TEXTURES_PATH
        / Path(output_texture_path + suffix + constants.TEXTURE_EXTENSION),
        output_texture_path=output_texture_path,
        offset=meta["offset"],
        visibility=meta["visibility"],
        options=meta["options"],
        manual_parent_model=meta["manual_parent_model"],
        omnidirectional_parent=meta["omnidirectional_parent"],
    )


# --------------------------------------------------------------------------
# Stage 2: objmc's command line
# --------------------------------------------------------------------------


def _objmc_argv(plan: ConversionPlan, objmc_path) -> list[str]:
    """The command line objmc is invoked with. Version-specific."""
    argv = [
        # objmc must run under the interpreter running this script, not whatever
        # "python3" resolves to on PATH - it imports PIL, which is installed
        # per-environment.
        sys.executable,
        str(objmc_path),
        "--obj",
        str(plan.obj_file).replace("\\", "/"),
        "--tex",
        str(plan.texture_file).replace("\\", "/"),
        "--offset",
        plan.offset[0],
        plan.offset[1],
        plan.offset[2],
        "--out",
        str(plan.output_model_file).replace("\\", "/"),
        str(plan.output_texture_file).replace("\\", "/"),
        "--visibility",
        str(plan.visibility),
    ]
    if "noshadow" in plan.options:
        argv.append("--noshadow")
    if "flipuv" in plan.options:
        argv.append("--flipuv")
    return argv


def _run_objmc(plan: ConversionPlan, objmc_path) -> bool:
    """Run objmc. False means it failed and nothing should be written."""
    try:
        result = subprocess.run(
            _objmc_argv(plan, objmc_path),
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        util.printDebug("objmc Script result: " + str(result.returncode), False)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error running process script: {e}")
        print(
            "Script output (stdout):",
            e.stdout.decode("utf-8") if e.stdout else "No stdout",
        )
        print(
            "Script error output (stderr):",
            e.stderr.decode("utf-8") if e.stderr else "No stderr",
            flush=True,
        )
        return False


# --------------------------------------------------------------------------
# Stage 3: fit objmc's output into our pack
# --------------------------------------------------------------------------


def _reshape_output(plan: ConversionPlan) -> dict:
    """objmc's model JSON, rewritten to our pack's conventions.

    Tied to objmc's output format: it assumes `textures` and `display` exist.
    """
    with open(plan.output_model_file, "r") as output_model_json:
        data = json.load(output_model_json)

    baked_texture = (
        constants.MCME_NAMESPACE + ":" + plan.output_texture_path + plan.suffix
    )
    data["textures"]["0"] = baked_texture
    data["textures"]["particle"] = baked_texture
    # Only rendered in the world, so the item-context properties are dropped.
    # Both are conditional: objmc emitted `display` before the 2026 rewrite and
    # does not now, so the key may or may not be there.
    if "display" in data:
        del data["display"]
    if "gui_light" in data:
        del data["gui_light"]
    util.remove_tintindex(data)
    return data


def _copy_override_parent(input_path, output_path, parent_model) -> bool:
    """Copy a parent model out of the override layer. False if it isn't there."""
    override_model_file = (
        input_path
        / constants.RELATIVE_VANILLA_OVERRIDES_PATH
        / constants.RELATIVE_SODIUM_MODELS_PATH
        / Path(parent_model + constants.VANILLA_MODEL_EXTENSION)
    )
    if not override_model_file.exists():
        return False
    shutil.copy(
        override_model_file,
        output_path
        / constants.RELATIVE_SODIUM_MODELS_PATH
        / Path(parent_model + constants.VANILLA_MODEL_EXTENSION),
    )
    return True


def _rotated_parent_name(plan: ConversionPlan, manual_parent_model: str) -> str:
    """The parent variant matching this model's rotation.

    An omnidirectional parent looks the same from every angle, so it keeps its
    plain name; everything else has a per-rotation variant named `_1_<n>`.
    """
    if plan.rotation is None or plan.omnidirectional_parent:
        return manual_parent_model
    axis, angle = plan.rotation
    if axis != "y" or angle <= 0:
        return manual_parent_model
    if not bool(re.search(r"_[0-9]+$", manual_parent_model)):
        manual_parent_model = manual_parent_model + "_1"
    return manual_parent_model + "_" + str(angle // 90 + 1)


def _apply_manual_parent(input_path, output_path, plan, data, debug):
    """Point the model at the parent its .objmeta names, copying it across."""
    del data["elements"]
    original_manual_parent = plan.manual_parent_model
    util.printDebug("        Manual parent: " + original_manual_parent, debug)

    manual_parent_model = _rotated_parent_name(plan, original_manual_parent)
    if manual_parent_model != original_manual_parent:
        util.printDebug("        Rotated parent: " + manual_parent_model, debug)

    data["parent"] = constants.MCME_NAMESPACE + ":" + manual_parent_model
    if manual_parent_model not in converted_models:
        if not _copy_override_parent(input_path, output_path, manual_parent_model):
            # The rotated variant doesn't exist, so fall back to the unrotated
            # parent - visibly wrong in game, but better than a missing model.
            print(
                f"        WARNING!!! Expected parent file {manual_parent_model} not found! Using: "
                + original_manual_parent,
                flush=True,
            )
            data["parent"] = constants.MCME_NAMESPACE + ":" + original_manual_parent
            if original_manual_parent not in converted_models:
                if not _copy_override_parent(
                    input_path, output_path, original_manual_parent
                ):
                    print(
                        f"        ERROR!!! Expected parent file {original_manual_parent} not found!",
                        flush=True,
                    )
        converted_models[manual_parent_model] = constants.PARENT_DONE_VALUE


def _extract_shared_parent(output_path, plan, data, compress):
    """Split the geometry of an already-converted model into a shared parent.

    Reached when the same model_path is converted a second time - typically the
    same model at another rotation. Both conversions then become children of one
    `*_parent` file holding the elements, so the geometry is stored once.
    """
    del data["elements"]
    parent_identifier = (
        constants.MCME_NAMESPACE + ":" + plan.model_path + constants.PARENT_SUFFIX
    )
    data["parent"] = parent_identifier

    first_model_file = converted_models[plan.model_path]
    if first_model_file == constants.PARENT_DONE_VALUE:
        # The parent was extracted on an earlier pass; nothing left to split.
        return

    with open(first_model_file, "r") as first_model_json:
        first_model_data = json.load(first_model_json)
    parent_model_data = first_model_data.copy()
    del parent_model_data["textures"]
    del first_model_data["elements"]
    first_model_data["parent"] = parent_identifier

    _write_model(Path(first_model_file), first_model_data, compress)
    _write_model(
        output_path
        / constants.RELATIVE_SODIUM_MODELS_PATH
        / Path(
            plan.model_path
            + constants.PARENT_SUFFIX
            + constants.VANILLA_MODEL_EXTENSION
        ),
        parent_model_data,
        compress,
    )


def _write_model(path: Path, data, compress):
    with open(path, "w") as f:
        if compress:
            json.dump(data, f, separators=(",", ":"))  # type: ignore
        else:
            json.dump(data, f, indent=4)  # type: ignore


# --------------------------------------------------------------------------
# The conversion
# --------------------------------------------------------------------------


def convert_sodium_model(
    input_path,
    output_path,
    model_path,
    rotation: tuple[str, float] | None,
    objmc_path,
    compress,
    debug,
):
    util.printDebug(f"    Converting model: {model_path} rotation: {rotation}", debug)

    plan = _plan_conversion(input_path, output_path, model_path, rotation)
    if plan is None:
        return

    if plan.rotation is not None:
        axis, angle = plan.rotation
        # objmc has no rotation of its own, so the rotation is baked into a
        # temporary .obj for it to read. Removed again at the end.
        rotate_obj.rotate_obj_file(
            plan.source_obj_file, plan.obj_file, axis, -angle
        )

    os.makedirs(os.path.dirname(plan.output_model_file), exist_ok=True)
    os.makedirs(os.path.dirname(plan.output_texture_file), exist_ok=True)

    if _run_objmc(plan, objmc_path):
        data = _reshape_output(plan)

        if plan.manual_parent_model:
            _apply_manual_parent(input_path, output_path, plan, data, debug)
        elif model_path in converted_models:
            _extract_shared_parent(output_path, plan, data, compress)
            converted_models[model_path] = constants.PARENT_DONE_VALUE
        else:
            converted_models[model_path] = plan.output_model_file

        _write_model(plan.output_model_file, data, compress)

    if plan.rotation is not None:
        Path(plan.obj_file).unlink()
