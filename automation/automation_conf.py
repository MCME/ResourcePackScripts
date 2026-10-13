"""An automation folder's automation.conf: what may differ between test and production.

One `key=value` per line; `#` starts a comment. Every key is required and every
value is checked, so a typo is refused by name instead of silently changing how
a release behaves. install.py writes the file; the launcher reads it with

    python3 automation_conf.py get <automation.conf> <key>

which prints the value on stdout and exits 0, or prints the reason on stderr,
leaves stdout empty and exits 2.
"""

import re
import sys
from pathlib import Path

# A branch name made only of characters no shell needs quoted, never starting
# with "-" (it would read as an option) and never HEAD (no branch is called
# that). git refuses some other names that match, such as a..b; no checkout
# can be on one, so the launcher's branch check stops those.
_BRANCH = re.compile(r"(?!HEAD\Z)[A-Za-z0-9][A-Za-z0-9._/-]*")

# Each setting, and the values it may take (None: a branch name)
SETTINGS = {
    "side": ("test", "production"),
    "branch": None,
    "replace_existing": ("yes", "no"),
    "wrapper": ("yes", "no"),
}

# What install.py writes for each side
DEFAULTS = {
    "test": {"side": "test", "branch": "development", "replace_existing": "yes", "wrapper": "yes"},
    "production": {"side": "production", "branch": "master", "replace_existing": "no", "wrapper": "yes"},
}

_EXPLAINED = {
    "side": "test | production",
    "branch": "the branch ResourcePackScripts follows in this folder",
    "replace_existing": "may a re-run with an existing tag replace its zips? yes | no",
    "wrapper": "run releases through the pipeline wrapper? yes | no",
}


class ConfError(ValueError):
    """An automation.conf that can't be used."""


def parse(text):
    """The settings in automation.conf text, or ConfError naming what's wrong."""
    settings = {}
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        key, equals, value = (part.strip() for part in line.partition("="))
        if not equals or not key:
            raise ConfError(f"line {number}: expected key=value, found {raw.strip()!r}")
        if key not in SETTINGS:
            raise ConfError(f"line {number}: unknown setting {key!r}")
        if key in settings:
            raise ConfError(f"line {number}: {key} is set twice")
        allowed = SETTINGS[key]
        if allowed is None and not _BRANCH.fullmatch(value):
            raise ConfError(
                f"line {number}: {value!r} isn't a usable branch name "
                "(letters, digits and . _ / -, starting with a letter or digit, and not HEAD)"
            )
        if allowed is not None and value not in allowed:
            raise ConfError(f"line {number}: {key} must be {' or '.join(allowed)}, not {value!r}")
        settings[key] = value
    missing = [key for key in SETTINGS if key not in settings]
    if missing:
        raise ConfError("missing setting(s): " + ", ".join(missing))
    return settings


def read(path):
    """The settings in the automation.conf at path."""
    try:
        # utf-8-sig: an editor's byte order mark would otherwise glue onto the first key
        text = Path(path).read_text(encoding="utf-8-sig")
    except OSError as e:
        raise ConfError(f"can't read {path}: {e.strerror}") from e
    except UnicodeDecodeError as e:
        raise ConfError(f"{path} isn't UTF-8 text ({e.reason})") from e
    return parse(text)


def render(settings):
    """automation.conf text for these settings, each one explained."""
    parse("".join(f"{key}={value}\n" for key, value in settings.items()))
    lines = [
        "# What this automation folder does differently. Written by install.py;",
        "# see ResourcePackScripts/automation/automation.conf.example.",
    ]
    lines += [f"{key}={settings[key]}".ljust(27) + f" # {_EXPLAINED[key]}" for key in SETTINGS]
    text = "\n".join(lines) + "\n"
    # parse() ends a value at "#" and strips spaces, so "dev#x" passes the check
    # above and would read back as "dev": refuse what wouldn't read back as given
    for key, value in parse(text).items():
        if value != settings[key]:
            raise ConfError(f"{key} {settings[key]!r} would read back as {value!r}")
    return text


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 3 or args[0] != "get" or args[2] not in SETTINGS:
        print(f"usage: automation_conf.py get <automation.conf> <{'|'.join(SETTINGS)}>", file=sys.stderr)
        return 2
    try:
        settings = read(args[1])
    except ConfError as e:
        print(f"automation.conf: {e}", file=sys.stderr)
        return 2
    print(settings[args[2]])
    return 0


if __name__ == "__main__":
    sys.exit(main())
