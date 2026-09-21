"""Output placement contract.

:class:`PlacementPolicy` lives here because the use case derives it from
settings; only the adapter knows how to honour it.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class PlacementPolicy:
    # None means "stage in the destination directory", which is what you want
    # unless the library is on NFS/SMB or a union filesystem.
    scratch_dir: Path | None = None
    # Source and staged output coexist during the mux, plus a little headroom.
    free_space_factor: float = 1.05
    preserve_ownership: bool = True


class Placement(Protocol):
    def ensure_free_space(
        self, destination_dir: Path, required_bytes: int, *, factor: float
    ) -> None: ...

    def staged_output(
        self, destination: Path, policy: PlacementPolicy | None = None
    ) -> AbstractContextManager[Path]: ...

    def finalise(
        self, staging: Path, destination: Path, policy: PlacementPolicy | None = None
    ) -> Path: ...

    def copy_attributes(
        self, reference: Path, target: Path, policy: PlacementPolicy | None = None
    ) -> None: ...
