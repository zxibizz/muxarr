"""Put the muxed result at its final path safely.

Two rules hold this together:

* the staging file lives in the *destination* directory by default, so the final
  step is a metadata-only rename and *arr's follow-up move cannot degrade into a
  cross-device copy of the whole file;
* nothing is ever written or unlinked outside that destination directory.
"""

from __future__ import annotations

import logging
import os
import secrets
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from muxarr.errors import InsufficientSpaceError, PlacementError

log = logging.getLogger(__name__)

STAGING_SUFFIX = ".part"


@dataclass(frozen=True, slots=True)
class PlacementPolicy:
    # None means "stage in the destination directory", which is what you want
    # unless the library is on NFS/SMB or a union filesystem.
    scratch_dir: Path | None = None
    # Source and staged output coexist during the mux, plus a little headroom.
    free_space_factor: float = 1.05
    preserve_ownership: bool = True


def ensure_free_space(
    destination_dir: Path,
    required_bytes: int,
    *,
    factor: float = 1.05,
) -> None:
    """Raise if the destination filesystem cannot hold the result."""
    needed = int(required_bytes * factor)
    try:
        free = shutil.disk_usage(destination_dir).free
    except OSError as exc:
        raise PlacementError(f"cannot stat filesystem at {destination_dir}: {exc}") from exc

    if free < needed:
        raise InsufficientSpaceError(
            f"{destination_dir} has {free} bytes free, need {needed}"
        )


def staging_path_for(destination: Path, scratch_dir: Path | None = None) -> Path:
    """Unique staging path; keeps the real extension so mkvmerge picks the format."""
    directory = scratch_dir or destination.parent
    token = secrets.token_hex(4)
    return directory / f".muxarr-{os.getpid()}{token}-{destination.name}{STAGING_SUFFIX}"


@contextmanager
def staged_output(destination: Path, policy: PlacementPolicy | None = None) -> Iterator[Path]:
    """Yield a staging path, guaranteeing it is not left behind."""
    policy = policy or PlacementPolicy()
    staging = staging_path_for(destination, policy.scratch_dir)
    staging.parent.mkdir(parents=True, exist_ok=True)
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        yield staging
    finally:
        _unlink_quietly(staging)


def same_filesystem(left: Path, right: Path) -> bool:
    try:
        return left.stat().st_dev == right.stat().st_dev
    except OSError:
        return False


def finalise(staging: Path, destination: Path, policy: PlacementPolicy | None = None) -> Path:
    """Move the staged file onto ``destination``, atomically where possible."""
    policy = policy or PlacementPolicy()

    if not staging.is_file():
        raise PlacementError(f"staged file missing: {staging}")

    if same_filesystem(staging.parent, destination.parent):
        staging.replace(destination)
        return destination

    log.warning(
        "scratch dir %s is on a different filesystem to %s; falling back to copy. "
        "This doubles IO and loses atomicity - prefer leaving scratch_dir unset.",
        staging.parent,
        destination.parent,
    )
    _copy_then_replace(staging, destination)
    return destination


def _copy_then_replace(staging: Path, destination: Path) -> None:
    intermediate = staging_path_for(destination)
    try:
        shutil.copyfile(staging, intermediate)
        with intermediate.open("rb") as handle:
            os.fsync(handle.fileno())
        intermediate.replace(destination)
    except OSError as exc:
        _unlink_quietly(intermediate)
        raise PlacementError(f"could not place {destination}: {exc}") from exc


def copy_attributes(reference: Path, target: Path, policy: PlacementPolicy | None = None) -> None:
    """Mirror permissions (and ownership, if permitted) from the source file.

    *arr applies its own chmod/chown to the path it originally chose, which is not
    the path we produce when the extension changes -- so muxarr has to do it.
    """
    policy = policy or PlacementPolicy()
    try:
        stat = reference.stat()
    except OSError as exc:
        log.warning("cannot stat %s for attribute copy: %s", reference, exc)
        return

    try:
        target.chmod(stat.st_mode & 0o7777)
    except OSError as exc:
        log.warning("could not chmod %s: %s", target, exc)

    if not policy.preserve_ownership:
        return
    try:
        os.chown(target, stat.st_uid, stat.st_gid)
    except (OSError, AttributeError) as exc:
        # Expected whenever muxarr is not root and does not own the target.
        log.debug("could not chown %s: %s", target, exc)


def _unlink_quietly(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        log.warning("could not remove staging file %s: %s", path, exc)
