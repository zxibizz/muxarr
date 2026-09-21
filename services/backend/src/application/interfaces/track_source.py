"""Sidecar discovery contract."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from src.domain.media import ExternalTrack
from src.domain.naming import EpisodeRef


class TrackDiscovery(Protocol):
    def discover(
        self, video_path: Path, *, episode: EpisodeRef | None = None
    ) -> list[ExternalTrack]: ...
