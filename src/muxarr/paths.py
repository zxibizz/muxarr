"""Two-sided path containment.

The daemon takes file paths from an HTTP client and runs subprocesses on them, so
every path is checked before use:

* **reads** must resolve inside one of the configured ``read_roots``;
* **writes** must resolve inside the directory of the request's own destination,
  which must itself be inside ``read_roots``.

Resolution happens before the check, so a symlink pointing out of a root is
rejected rather than followed.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from muxarr.errors import PathNotAllowedError


def resolve(path: Path) -> Path:
    """Fully resolve a path, following symlinks, without requiring it to exist."""
    return Path(path).expanduser().resolve()


def is_within(candidate: Path, root: Path) -> bool:
    """True when ``candidate`` is ``root`` or sits underneath it.

    Both arguments must already be resolved.
    """
    return candidate == root or candidate.is_relative_to(root)


@dataclass(frozen=True, slots=True)
class PathGuard:
    read_roots: tuple[Path, ...]

    @classmethod
    def from_roots(cls, roots: Sequence[Path]) -> PathGuard:
        return cls(read_roots=tuple(resolve(root) for root in roots))

    def check_read(self, path: Path) -> Path:
        """Resolve ``path`` and confirm it is readable, or raise."""
        resolved = resolve(path)
        if not any(is_within(resolved, root) for root in self.read_roots):
            raise PathNotAllowedError(
                f"{path} resolves to {resolved}, which is outside every configured read root"
            )
        return resolved

    def check_destination(self, destination: Path) -> Path:
        """Resolve a destination file path and confirm muxarr may create it."""
        resolved = resolve(destination)
        if not any(is_within(resolved, root) for root in self.read_roots):
            raise PathNotAllowedError(
                f"destination {destination} resolves to {resolved}, "
                "which is outside every configured read root"
            )
        if resolved in self.read_roots:
            raise PathNotAllowedError(f"destination {destination} is a configured root itself")
        return resolved

    def check_write(self, path: Path, destination: Path) -> Path:
        """Confirm ``path`` may be written, given the request's destination.

        The only directory muxarr ever writes to is the destination's own parent;
        this is what keeps a malformed request from touching anything else.
        """
        resolved = resolve(path)
        write_root = self.check_destination(destination).parent
        if not is_within(resolved, write_root):
            raise PathNotAllowedError(
                f"{path} resolves to {resolved}, which is outside the write root {write_root}"
            )
        return resolved
