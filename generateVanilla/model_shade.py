"""Keeps unshaded model elements unshaded on 26.3 (docs/conversion.md).

Up to 26.2 an element with "shade": false is drawn at full brightness. 26.3
no longer reads that key: it reads "shade_direction_override", the face
direction whose brightness the element takes, and vanilla's own models moved
to "up" (full brightness, as before). An element with only "shade": false is
shaded by its faces' directions on 26.3, on vanilla and Sodium alike: 0.8 for
north and south, 0.6 for east and west - grass and leaves 20-40% darker.

Each version ignores the other's key, so an element carries both and looks
the same on 26.2 and 26.3. add_override writes the new key on the line after
the old one, so the file keeps its indentation, line endings and key order.
"""

import json
import re
from pathlib import Path

OVERRIDE_KEY = "shade_direction_override"
# The direction whose brightness "shade": false gave up to 26.2
OVERRIDE_VALUE = "up"

# "shade": false on a line of its own, as every pack writes it
SHADE_FALSE_LINE = re.compile(r'^([ \t]*)"shade"[ \t]*:[ \t]*false[ \t]*(,?)[ \t]*(\r?\n|$)', re.M)


class ModelShadeError(Exception):
    pass


def unshaded_elements(model):
    """Each element of the model with "shade": false, in file order, and whether it has the override."""
    elements = model.get("elements") if isinstance(model, dict) else None
    if not isinstance(elements, list):
        return []
    return [
        OVERRIDE_KEY in element
        for element in elements
        if isinstance(element, dict) and element.get("shade") is False
    ]


def missing_override(text):
    """How many "shade": false elements of a model file lack the override."""
    try:
        model = json.loads(text)
    except ValueError:
        return 0
    return unshaded_elements(model).count(False)


def add_override(text):
    """The model file with the override added to each "shade": false element that lacks it."""
    has_override = unshaded_elements(json.loads(text))
    lines = list(SHADE_FALSE_LINE.finditer(text))
    if len(lines) != len(has_override):
        raise ModelShadeError(
            f'{len(has_override)} elements have "shade": false, but {len(lines)} lines say so on their own'
        )
    parts = []
    end = 0
    for line, done in zip(lines, has_override):
        if done:
            continue
        indent, comma, newline = line.groups()
        newline = newline or "\n"
        parts.append(text[end : line.start()])
        parts.append(
            f'{indent}"shade": false,{newline}'
            f'{indent}"{OVERRIDE_KEY}": "{OVERRIDE_VALUE}"{comma}{line.group(3)}'
        )
        end = line.end()
    parts.append(text[end:])
    return "".join(parts)


def model_files(pack_path):
    """Every block and item model of a pack: assets/ and its overlays alike."""
    for path in sorted(Path(pack_path).rglob("*.json")):
        relative = path.relative_to(pack_path).parts
        if ".git" not in relative and "models" in relative:
            yield path


def read(path):
    # newline="" keeps CRLF files CRLF
    with open(path, encoding="utf-8-sig", newline="") as f:
        return f.read()


def check(pack_path):
    """{model path: elements missing the override} for the whole pack."""
    missing = {}
    for path in model_files(pack_path):
        count = missing_override(read(path))
        if count:
            missing[path] = count
    return missing


def fix(pack_path):
    """Adds the override throughout the pack; {model path: elements fixed}."""
    fixed = check(pack_path)
    for path in fixed:
        raw = Path(path).read_bytes()
        bom = raw.startswith(b"\xef\xbb\xbf")
        try:
            text = add_override(read(path))
        except ModelShadeError as e:
            raise ModelShadeError(f"{path}: {e}") from e
        with open(path, "w", encoding="utf-8-sig" if bom else "utf-8", newline="") as f:
            f.write(text)
    return fixed
