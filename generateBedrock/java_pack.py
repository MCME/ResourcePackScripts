"""Reading a Java resource pack the way the client does: the pack over vanilla.

A Bedrock custom block replaces the whole Java block state, so it needs every
model and texture the state is drawn from, the pack's own and vanilla's alike.
Everything is looked up in the pack first and then in the vanilla client's
resources (the same `Vanilla-26.2` folder generateVanilla walks).

The pack is input from many hands (README, "Running it safely"): a path built
from pack content is followed only while it stays inside the pack, and a file
that can't be read is reported and skipped, never fatal.
"""

import json
from pathlib import Path

MCME_NAMESPACE = "mcme"
VANILLA_NAMESPACE = "minecraft"


def split_identifier(identifier: str, default_namespace: str = VANILLA_NAMESPACE) -> tuple[str, str]:
    if ":" in identifier:
        namespace, path = identifier.split(":", 1)
        return namespace, path
    return default_namespace, identifier


def full_identifier(identifier: str, default_namespace: str = VANILLA_NAMESPACE) -> str:
    return "{}:{}".format(*split_identifier(identifier, default_namespace))


def contained_path(root: Path, relative) -> Path | None:
    """`root / relative`, resolved - or None when that leads outside `root`.

    The same rule as generateVanilla's util.contained_path: `..`, an absolute
    path or a symlink in pack content could otherwise point anywhere.
    """
    root = Path(root).resolve()
    path = (root / relative).resolve()
    return path if path.is_relative_to(root) else None


class Assets:
    """The pack's and vanilla's assets, and what was wrong with any of them."""

    def __init__(self, pack: Path, vanilla: Path, warn):
        self.pack = Path(pack)
        self.vanilla = Path(vanilla)
        self.warn = warn
        self._json_cache: dict[Path, object] = {}
        self._outside_reported: set[str] = set()

    def _find(self, relative: str, pack_only: bool = False) -> tuple[Path, bool] | None:
        """(file, whether it's the pack's) for a path under each root's folder."""
        path = contained_path(self.pack, relative)
        if path is None:
            if relative not in self._outside_reported:
                self._outside_reported.add(relative)
                self.warn(f"{relative} leads outside the pack - skipping it")
            return None
        if path.is_file():
            return path, True
        if pack_only:
            return None
        path = contained_path(self.vanilla, relative)
        if path is not None and path.is_file():
            return path, False
        return None

    def read_json(self, path: Path):
        """A JSON file's content, or None (with a warning) when it isn't valid JSON."""
        if path not in self._json_cache:
            try:
                with open(path, encoding="utf-8-sig") as f:
                    self._json_cache[path] = json.load(f)
            except (OSError, ValueError) as e:
                self.warn(f"Couldn't read {self._shown(path)}: {e}")
                self._json_cache[path] = None
        return self._json_cache[path]

    def _shown(self, path: Path) -> str:
        for root in (self.pack, self.vanilla):
            try:
                return str(Path(path).resolve().relative_to(root.resolve()))
            except ValueError:
                continue
        return str(path)

    # ----------------------------------------------------------------------

    def blockstate(self, block_path: str) -> tuple[Path, bool] | None:
        return self._find(f"assets/minecraft/blockstates/{block_path}.json")

    def vanilla_blockstate(self, block_path: str) -> Path | None:
        path = contained_path(self.vanilla, f"assets/minecraft/blockstates/{block_path}.json")
        return path if path is not None and path.is_file() else None

    def model(self, identifier: str) -> tuple[Path, bool] | None:
        namespace, path = split_identifier(identifier)
        return self._find(f"assets/{namespace}/models/{path}.json")

    def texture(self, identifier: str) -> tuple[Path, bool] | None:
        namespace, path = split_identifier(identifier)
        return self._find(f"assets/{namespace}/textures/{path}.png")

    def mcme_file(self, relative: str) -> Path | None:
        """A file of the pack's mcme namespace: .obj, .mtl and .objmeta live only there."""
        found = self._find(f"assets/{MCME_NAMESPACE}/{relative}", pack_only=True)
        return found[0] if found else None
