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
3. `_reshape_output` and `_extract_shared_parent` - take the model JSON objmc
   produced, fix it into our pack's conventions and link up parents.
   `_reshape_output` is **objmc's output format**; the parent linking is purely
   our own. A parent is never pre-baked or copied from elsewhere - it is
   whatever geometry objmc itself produced for the first model that read a
   given source .obj, split out the moment a second model (same .obj, same
   rotation) is converted and found to share it. See `_parent_identifier` for
   how models are grouped.

A texture animated by its `.mcmeta` (a vanilla flipbook) is baked frame by
frame: objmc only ever sees the first frame, and `_bake_flipbook` then stacks
one copy of that bake per source frame, swapping in each frame's pixels. The
client flips through whole bakes, so the shader always reads a complete,
identically laid out one. See `Flipbook`.

That split is what makes an objmc upgrade tractable: a change lands in stage 2
or stage 3, and which one it lands in tells you whether objmc's CLI moved or
its output did. Stages 1 and the parent linking should not need to move at all.

The golden tests in tests/test_objmc_golden.py pin stage 2 and 3 against a real
objmc. Everything else is covered by the faked-subprocess tests.
"""

import copy
import json
import math
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field, replace
from pathlib import Path

import constants
import rotate_obj
import util
import yaml

# parent identifier -> the _ParentGroup tracking it. The identifier is derived
# from the source .obj file a model reads (see `_parent_identifier`), not from
# the model's own name, so two differently-named models reading the same .obj
# (e.g. pine_leaves_brown and maple_leaves both reading leaves_parent.obj) are
# recognised as sharing geometry. Module-level because a model can be reached
# from more than one traversal root, and the second visit is what triggers
# parent extraction.
converted_models = {}


@dataclass
class _ParentGroup:
    """One parent identifier's state: its texture size, and its file until split.

    objmc lays out the position/uv data it embeds in the baked texture relative
    to that texture's own pixel width (see objmc.py's `tw`), so two bakes only
    encode compatible offsets when their output textures are the same size.
    `texture_size` is what `convert_sodium_model` checks before trusting a
    borrowed `elements` array; a mismatch would otherwise read as near-black
    noise in game rather than the intended geometry.
    """

    # The file the first model in this group was written to, or None once its
    # elements have been split out into an actual `*_parent` file on disk.
    file: Path | None
    texture_size: tuple[int, int]


# The suffix identifying a rotated variant of a model. Shared by the rotated
# .obj, the converted model and its texture, so they all have to agree.
def rotation_suffix(rotation: tuple[str, float] | None):
    if rotation is None:
        return ""
    axis, angle = rotation
    return f"_{axis}_{angle}"


@dataclass
class Flipbook:
    """A source texture the client animates through its `.mcmeta`.

    The .obj's UVs map onto a single frame, never the whole sheet, so objmc must
    only see one frame. The output is then a flipbook of whole bakes - one per
    source frame, each identical but for its texture section - because the atlas
    only ever holds the current frame, and the shader finds the geometry data
    relative to that frame.
    """

    # The whole source .mcmeta, carried into the output with its animation
    # section fitted to the baked frame size.
    mcmeta: dict
    frame_size: tuple[int, int]
    # Frames in vanilla's order: left to right, then top to bottom.
    frame_count: int


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
    # The pack-relative, suffix-stripped identifier of the .obj this model was
    # read from (e.g. "block/leaves_parent"). This is what ties two
    # differently-named models together as sharing one parent.
    obj_model_path: str
    offset: list = field(default_factory=lambda: ["-0.5", "0.0", "-0.5"])
    visibility: int = 7
    options: list = field(default_factory=list)
    omnidirectional_parent: bool = False
    # Set when the source texture is animated by its .mcmeta.
    flipbook: Flipbook | None = None


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


def _flipbook_frame_size(animation: dict, width: int, height: int):
    """The size of one frame, as the client would cut it from the sheet.

    Follows vanilla (AnimationMetadataSection.calculateFrameSize): an explicit
    `width`/`height` wins, the missing one falling back to the whole sheet's;
    with neither, frames are square. The `frames` list never changes the cut -
    the .obj's UVs were authored against the frame the client actually shows,
    so cutting any other size stretches the texture across every face. An index
    the cut does not reach is dropped instead, see `_frame_index`.
    """
    if "width" in animation or "height" in animation:
        return animation.get("width", width), animation.get("height", height)
    size = min(width, height)
    return size, size


def _frame_index(frame) -> int:
    """The sheet index of one entry of an animation's `frames` list."""
    return frame["index"] if isinstance(frame, dict) else frame


def _read_flipbook(texture_file: Path) -> Flipbook | None:
    """The texture's flipbook animation, or None if the client never animates it."""
    mcmeta_file = Path(str(texture_file) + constants.MCMETA_EXTENSION)
    if not mcmeta_file.exists() or not texture_file.exists():
        return None
    with open(mcmeta_file, "r", encoding="utf-8-sig") as f:
        mcmeta = json.load(f)
    animation = mcmeta.get("animation")
    if not isinstance(animation, dict):
        return None

    width, height = _texture_size(texture_file)
    frame_width, frame_height = _flipbook_frame_size(animation, width, height)
    if (
        frame_width <= 0
        or frame_height <= 0
        or width % frame_width
        or height % frame_height
    ):
        print(
            f"        WARNING!!! {texture_file} ({width}x{height}) does not divide "
            f"into {frame_width}x{frame_height} frames - baking it unanimated.",
            flush=True,
        )
        return None

    frame_count = (width // frame_width) * (height // frame_height)
    if frame_count < 2:
        return None
    return Flipbook(mcmeta, (frame_width, frame_height), frame_count)


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

    texture_file = (
        input_path
        / relative_texture_path
        / Path(texture_path + constants.TEXTURE_EXTENSION)
    )

    return ConversionPlan(
        model_path=model_path,
        rotation=rotation,
        suffix=suffix,
        obj_file=sodium_models
        / Path(obj_model_path + suffix + constants.OBJ_MODEL_EXTENSION),
        source_obj_file=source_obj_file,
        texture_file=texture_file,
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
        obj_model_path=obj_model_path,
        omnidirectional_parent=meta["omnidirectional_parent"],
        flipbook=_read_flipbook(texture_file),
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
        "--mipmap",
        str(constants.OBJMC_MIPMAP_LEVELS),
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


def _is_parent_obj(obj_model_path: str) -> bool:
    """Whether a source .obj is meant to be shared as a parent.

    Only .obj files already named as parents by convention are - `parent`,
    `leaves_parent`, or a numbered variant such as `parent_2` or
    `leaves_parent_3`. Any other .obj, numbered or not (`lamp`, `lamp_2`),
    keeps its geometry in its own models and never becomes a parent.
    """
    return bool(re.search(r"(?:^|[/_])parent(?:_[0-9]+)?$", obj_model_path))


def _parent_identifier(plan: ConversionPlan) -> str | None:
    """The parent this conversion groups under, rotation included.

    None when the source .obj is not a parent (see `_is_parent_obj`).
    Otherwise it is named after the .obj itself, not the model reading it -
    two differently named models that read the same .obj (e.g.
    pine_leaves_brown and maple_leaves both reading leaves_parent.obj) group
    under this same name.

    An omnidirectional parent looks the same from every angle, so every
    rotation of it groups under the plain name; everything else groups under a
    per-rotation variant named `_1_<n>`, matching only when the same axis and
    angle recur (rotations sharing every other axis or a non-positive angle
    all fall back to the plain, unrotated name).
    """
    if not _is_parent_obj(plan.obj_model_path):
        return None
    base_name = plan.obj_model_path
    if plan.rotation is None or plan.omnidirectional_parent:
        return base_name
    axis, angle = plan.rotation
    if axis != "y" or angle <= 0:
        return base_name
    if not bool(re.search(r"_[0-9]+$", base_name)):
        base_name = base_name + "_1"
    return base_name + "_" + str(angle // 90 + 1)


def _texture_size(path: Path) -> tuple[int, int]:
    from PIL import Image

    with Image.open(path) as image:
        return image.width, image.height


def _flipbook_frames(plan: ConversionPlan) -> list:
    """The source texture's frames as RGBA images, in vanilla's order."""
    from PIL import Image

    frame_width, frame_height = plan.flipbook.frame_size
    with Image.open(plan.texture_file) as sheet:
        sheet = sheet.convert("RGBA")
        columns = sheet.width // frame_width
        return [
            sheet.crop(
                (
                    (i % columns) * frame_width,
                    (i // columns) * frame_height,
                    (i % columns + 1) * frame_width,
                    (i // columns + 1) * frame_height,
                )
            )
            for i in range(plan.flipbook.frame_count)
        ]


def _bake_texture_rows(start: int, texture_height: int, mipmap: int):
    """(first padding row, first texture row, first data row) of a bake.

    `start` is the row after the face pointers, `mipmap` the header's t[6].g.
    The same layout the shader's objmc_main.glsl decodes: with mipmapping, the
    texture starts on a 2^mipmap row boundary, padded by at least one such
    block of repeated edge rows either side.
    """
    if mipmap <= 0:
        return start, start, start + texture_height
    block = 1 << mipmap
    top = -(-(start + block) // block) * block
    return start, top, -(-(top + texture_height) // block) * block + block


def _bake_flipbook(plan: ConversionPlan, frames: list) -> bool:
    """Turn objmc's single-frame bake into one bake per source frame.

    The texture section is found from the bake's own header - the same fields
    the shader reads (texture size, vertex count), so this depends on the
    shader's data format rather than on how objmc lays it out. Its orientation
    is found by matching the first frame, which objmc was given. False means the
    bake could not be read, and it is left as a single, unanimated frame.
    """
    from PIL import Image

    with Image.open(plan.output_texture_file) as image:
        bake = image.convert("RGBA")
    header = [bake.getpixel((x, 0)) for x in range(8)]
    texture_width = header[1][0] * 256 + header[1][1]
    texture_height = header[1][2] * 256 + header[7][0]
    vertex_count = (
        header[2][0] * 16777216 + header[2][1] * 65536 + header[2][2] * 256 + header[7][1]
    )
    if header[0] != (12, 34, 56, 255) or (texture_width, texture_height) != frames[0].size:
        print(
            f"        WARNING!!! Unrecognised objmc bake for {plan.model_path} - "
            "leaving it unanimated.",
            flush=True,
        )
        return False
    start, top, data_top = _bake_texture_rows(
        2 + math.ceil(vertex_count / 4 / texture_width), texture_height, header[6][1]
    )
    box = (0, top, texture_width, top + texture_height)

    baked_section = bake.crop(box).tobytes()
    if baked_section == frames[0].tobytes():
        flip = False
    elif baked_section == frames[0].transpose(Image.FLIP_TOP_BOTTOM).tobytes():
        flip = True
    else:
        print(
            f"        WARNING!!! Could not find the texture in the objmc bake for "
            f"{plan.model_path} - leaving it unanimated.",
            flush=True,
        )
        return False

    flipbook = Image.new("RGBA", (bake.width, bake.height * len(frames)))
    for i, frame in enumerate(frames):
        baked_frame = bake.copy()
        baked_frame.paste(frame.transpose(Image.FLIP_TOP_BOTTOM) if flip else frame, box)
        # The mipmap padding repeats the texture's edge rows, so it has to
        # follow each frame's texture too.
        first_row = baked_frame.crop((0, top, texture_width, top + 1))
        last_row = baked_frame.crop(
            (0, top + texture_height - 1, texture_width, top + texture_height)
        )
        for y in range(start, top):
            baked_frame.paste(first_row, (0, y))
        for y in range(top + texture_height, data_top):
            baked_frame.paste(last_row, (0, y))
        flipbook.paste(baked_frame, (0, i * bake.height))
    flipbook.save(plan.output_texture_file)

    mcmeta = copy.deepcopy(plan.flipbook.mcmeta)
    animation = mcmeta["animation"]
    # Frames are whole bakes now, and rarely square.
    animation["width"] = bake.width
    animation["height"] = bake.height
    if "frames" in animation:
        # The client skips an index past the last frame with a warning in its
        # log; drop it here so the output loads cleanly but plays the same.
        frame_list = animation["frames"]
        animation["frames"] = [
            frame for frame in frame_list if 0 <= _frame_index(frame) < len(frames)
        ]
        if len(animation["frames"]) < len(frame_list):
            print(
                f"        Note: {plan.texture_file}.mcmeta lists frames past the "
                f"{len(frames)} its sheet holds - dropping them, as the client does.",
                flush=True,
            )
    if animation.get("interpolate"):
        # Interpolation blends every pixel of neighbouring frames, the geometry
        # data included - and the client's blend can round an unchanged value
        # down by one, shifting vertices.
        print(
            f"        Note: turning off interpolation for {plan.model_path} - "
            "blending would corrupt the baked geometry.",
            flush=True,
        )
        animation["interpolate"] = False
    with open(_output_mcmeta_file(plan), "w") as f:
        json.dump(mcmeta, f, indent=4)
    return True


def _output_mcmeta_file(plan: ConversionPlan) -> Path:
    return Path(str(plan.output_texture_file) + constants.MCMETA_EXTENSION)


def _extract_shared_parent(output_path, parent_name: str, group: "_ParentGroup", data, compress):
    """Split the geometry of an already-converted model into a shared parent.

    Reached when a second model grouping under the same parent name, and
    baked to the same texture size, is converted - either the same source .obj
    read by a differently named model, or the same model at another rotation.
    Both conversions then become children of one `*_parent` file holding the
    elements, so the geometry is generated and stored only once.
    """
    del data["elements"]
    parent_identifier = constants.MCME_NAMESPACE + ":" + parent_name
    data["parent"] = parent_identifier

    if group.file is None:
        # The parent was extracted on an earlier pass; nothing left to split.
        return

    with open(group.file, "r") as first_model_json:
        first_model_data = json.load(first_model_json)
    parent_model_data = first_model_data.copy()
    del parent_model_data["textures"]
    del first_model_data["elements"]
    first_model_data["parent"] = parent_identifier

    _write_model(group.file, first_model_data, compress)
    _write_model(
        output_path
        / constants.RELATIVE_SODIUM_MODELS_PATH
        / Path(parent_name + constants.VANILLA_MODEL_EXTENSION),
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
    # A .mcmeta left by an earlier export would have the client animate a bake
    # that now has a different frame size, or no frames at all.
    _output_mcmeta_file(plan).unlink(missing_ok=True)

    frames = None
    with tempfile.TemporaryDirectory() as temp_dir:
        objmc_plan = plan
        if plan.flipbook is not None:
            util.printDebug(
                f"        Flipbook: {plan.flipbook.frame_count} frames of "
                f"{plan.flipbook.frame_size}",
                debug,
            )
            frames = _flipbook_frames(plan)
            first_frame = Path(temp_dir) / ("frame_0" + constants.TEXTURE_EXTENSION)
            frames[0].save(first_frame)
            objmc_plan = replace(plan, texture_file=first_frame)
        converted = _run_objmc(objmc_plan, objmc_path)

    if converted:
        data = _reshape_output(plan)
        # Measured before the frames are stacked: the geometry a parent shares
        # depends on the size of one bake, not on how many frames it has.
        texture_size = _texture_size(plan.output_texture_file)
        if frames is not None:
            _bake_flipbook(plan, frames)

        parent_name = _parent_identifier(plan)
        group = converted_models.get(parent_name)
        if parent_name is None:
            pass  # Not a parent .obj: the model keeps its own geometry.
        elif group is not None and group.texture_size == texture_size:
            util.printDebug(f"        Shared parent: {parent_name}", debug)
            _extract_shared_parent(output_path, parent_name, group, data, compress)
            converted_models[parent_name] = _ParentGroup(None, texture_size)
        else:
            if group is not None:
                # Same parent group, but this bake's texture is a different
                # size - objmc's embedded position/uv offsets are relative to
                # the texture's own width, so borrowing the other bake's
                # elements here would read back as corrupted (near-black) noise
                # in game rather than the intended geometry. Keep this model's
                # own geometry instead of sharing.
                print(
                    f"        WARNING!!! {model_path} shares parent group "
                    f"{parent_name} but its baked texture is {texture_size}, "
                    f"not {group.texture_size} - not sharing a parent with it. "
                    "Make the source textures the same size to share geometry.",
                    flush=True,
                )
            converted_models[parent_name] = _ParentGroup(plan.output_model_file, texture_size)

        _write_model(plan.output_model_file, data, compress)

    if plan.rotation is not None:
        Path(plan.obj_file).unlink()
