"""Muxing contract.

:class:`MuxPlan` lives here rather than in the mkvmerge adapter because the use
case builds it; the adapter only consumes it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from src.domain.media import ExternalTrack, MediaInfo


@dataclass(frozen=True, slots=True)
class MuxPlan:
    source: Path
    output: Path
    tracks: tuple[ExternalTrack, ...]
    modern_flags: bool = True
    sub_charset: str | None = None
    title: str | None = None
    extra_args: tuple[str, ...] = field(default=())
    # mkvmerge IDs of the source's own tracks to keep; None keeps every one of that kind.
    keep_audio: tuple[int, ...] | None = None
    keep_subtitles: tuple[int, ...] | None = None

    @property
    def prunes_source(self) -> bool:
        return self.keep_audio is not None or self.keep_subtitles is not None


class Muxer(Protocol):
    def supports_modern_flags(self) -> bool: ...

    def run(self, plan: MuxPlan, source_info: MediaInfo, *, timeout: float) -> MediaInfo: ...
