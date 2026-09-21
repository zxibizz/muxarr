"""Probe backend selection.

Implements :class:`src.application.interfaces.prober.MediaProber` by trying
mkvmerge first and falling back to ffprobe.
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.domain.errors import ProbeError
from src.domain.media import MediaInfo
from src.infrastructure.ffmpeg.probe import probe_with_ffprobe
from src.infrastructure.mkvtoolnix.probe import probe_with_mkvmerge
from src.infrastructure.process.runner import has_tool

log = logging.getLogger(__name__)


def probe(path: Path) -> MediaInfo:
    """Inspect a container, preferring mkvmerge and falling back to ffprobe."""
    if not path.is_file():
        raise ProbeError(f"not a file: {path}")

    failures: list[str] = []

    if has_tool("mkvmerge"):
        try:
            return probe_with_mkvmerge(path)
        except ProbeError as exc:
            log.debug("mkvmerge could not probe %s (%s); trying ffprobe", path, exc)
            failures.append(f"mkvmerge: {exc}")

    if has_tool("ffprobe"):
        try:
            return probe_with_ffprobe(path)
        except ProbeError as exc:
            failures.append(f"ffprobe: {exc}")

    # Distinguish "the tools are missing" from "the tools rejected this file";
    # conflating them sends people installing software they already have.
    if failures:
        raise ProbeError("; ".join(failures))
    raise ProbeError(f"no probe backend available for {path}: install mkvtoolnix or ffmpeg")


class FallbackMediaProber:
    """Adapter object for the container; delegates to :func:`probe`."""

    def probe(self, path: Path) -> MediaInfo:
        return probe(path)
