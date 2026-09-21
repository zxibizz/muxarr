"""Container inspection contract."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from src.domain.media import MediaInfo


class MediaProber(Protocol):
    def probe(self, path: Path) -> MediaInfo: ...
