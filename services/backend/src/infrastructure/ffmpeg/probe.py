"""``ffprobe`` adapter.

The fallback for the odd container mkvmerge refuses to parse. Note that such a
file cannot be muxed either, so this only ever serves ``muxarr inspect``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.domain.enums import UNDETERMINED, TrackKind
from src.domain.errors import ProbeError
from src.domain.media import MediaInfo, Track
from src.infrastructure.process.json_output import load_json_object
from src.infrastructure.process.runner import resolve_tool, run

PROBE_TIMEOUT = 120.0

_FFPROBE_KIND: dict[str, TrackKind] = {
    "video": "video",
    "audio": "audio",
    "subtitle": "subtitles",
}


def probe_with_ffprobe(path: Path) -> MediaInfo:
    result = run(
        [
            resolve_tool("ffprobe"),
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_streams",
            "-show_format",
            str(path),
        ],
        timeout=PROBE_TIMEOUT,
    )
    if not result.ok:
        raise ProbeError(f"ffprobe failed for {path}: {result.tail()}")
    return parse_ffprobe_json(path, result.stdout)


def parse_ffprobe_json(path: Path, payload: str) -> MediaInfo:
    data = load_json_object(path, payload)

    tracks: list[Track] = []
    for stream in data.get("streams") or []:
        kind = _FFPROBE_KIND.get(str(stream.get("codec_type")))
        if kind is None:
            continue
        tags: dict[str, Any] = stream.get("tags") or {}
        disposition: dict[str, Any] = stream.get("disposition") or {}
        tracks.append(
            Track(
                index=int(stream.get("index", len(tracks))),
                kind=kind,
                codec_id=str(stream.get("codec_name") or ""),
                language=str(tags.get("language") or UNDETERMINED),
                name=tags.get("title") or None,
                default=bool(disposition.get("default", 0)),
                forced=bool(disposition.get("forced", 0)),
                hearing_impaired=bool(disposition.get("hearing_impaired", 0)),
            )
        )

    container = str((data.get("format") or {}).get("format_name") or "unknown")
    return MediaInfo(path=path, container=container, tracks=tuple(tracks))
