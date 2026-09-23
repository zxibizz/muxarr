"""Stand-ins for the ports HandleImportUseCase talks to."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from src.application.interfaces.muxer import MuxPlan
from src.domain.media import ExternalTrack, MediaInfo, Track
from src.domain.naming import EpisodeRef

VIDEO_ONLY = MediaInfo(
    path=Path("/x.mkv"),
    container="Matroska",
    tracks=(Track(index=0, kind="video", codec_id="V_MPEG4/ISO/AVC"),),
)


class StubProber:
    def __init__(
        self,
        error: Exception | None = None,
        *,
        empty: Sequence[Path] = (),
        infos: Mapping[Path, MediaInfo] | None = None,
    ) -> None:
        self._error = error
        self._empty = set(empty)
        self._infos = dict(infos or {})

    def probe(self, path: Path) -> MediaInfo:
        if self._error is not None:
            raise self._error
        if path in self._empty:
            return MediaInfo(path=path, container="Matroska", tracks=())
        return self._infos.get(path, VIDEO_ONLY)


class StubMuxer:
    """Writes the staged output instead of shelling out to mkvmerge."""

    def __init__(self, error: Exception | None = None) -> None:
        self.written: list[Path] = []
        self.plans: list[MuxPlan] = []
        self._error = error

    def supports_modern_flags(self) -> bool:
        return True

    def run(self, plan: MuxPlan, source_info: MediaInfo, *, timeout: float) -> MediaInfo:
        self.plans.append(plan)
        if self._error is not None:
            raise self._error
        plan.output.parent.mkdir(parents=True, exist_ok=True)
        plan.output.write_bytes(b"muxed")
        self.written.append(plan.output)
        return source_info


class StubDiscovery:
    def __init__(self, *tracks: ExternalTrack) -> None:
        self._tracks = list(tracks)

    def discover(
        self, video_path: Path, *, episode: EpisodeRef | None = None
    ) -> list[ExternalTrack]:
        return list(self._tracks)
