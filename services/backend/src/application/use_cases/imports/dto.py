"""Import request/outcome DTOs.

These cross every layer: the API parses into :class:`ImportRequest`, the use
case returns :class:`ImportOutcome`, and the shim protocol renders it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.domain.enums import App, MoveStatus
from src.domain.naming import EpisodeRef, parse_episode_marker

OUTPUT_SUFFIX = ".mkv"


@dataclass(frozen=True, slots=True)
class ImportRequest:
    app: App
    source_path: Path
    destination_path: Path
    transfer_mode: str = "Move"
    dry_run: bool = False

    @property
    def episode_ref(self) -> EpisodeRef | None:
        """Which episode this import is for, read off the filenames.

        The release name is the more reliable of the two: *arr's rename may drop
        the marker entirely under a custom naming format.
        """
        if self.app != "sonarr":
            return None
        for name in (Path(self.source_path).name, Path(self.destination_path).name):
            marker = parse_episode_marker(name)
            if marker is not None:
                return marker
        return None


@dataclass(frozen=True, slots=True)
class ImportOutcome:
    move_status: MoveStatus
    reason: str
    media_file: Path | None = None
    extra_files: tuple[Path, ...] = ()
    prevent_extra_import: bool = False
    added_tracks: tuple[str, ...] = ()
    # Why each discovered sidecar was passed over; the history UI shows these.
    rejected_tracks: tuple[dict[str, str], ...] = ()
    duration_ms: int = 0
    source_bytes: int | None = None
    output_bytes: int | None = None

    @property
    def deferred(self) -> bool:
        return self.move_status == "DeferMove"
