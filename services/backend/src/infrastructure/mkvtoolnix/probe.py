"""``mkvmerge -J`` adapter.

Preferred over ffprobe because it reports exactly the properties muxarr sets
back (``forced_track``, ``flag_hearing_impaired``), and because a file mkvmerge
cannot parse is a file it cannot mux either.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from src.domain.enums import UNDETERMINED
from src.domain.errors import ProbeError
from src.domain.media import MediaInfo, Track
from src.infrastructure.process.json_output import load_json_object
from src.infrastructure.process.runner import has_tool, resolve_tool, run

PROBE_TIMEOUT = 120.0

_MKVMERGE_VERSION_RE = re.compile(r"\bv(\d+)(?:\.(\d+))?")

# mkvtoolnix 58 renamed the flag options; older releases only accept the short forms.
MODERN_FLAG_SYNTAX_MIN_VERSION = 58


def mkvmerge_version() -> tuple[int, int] | None:
    """Major/minor of the installed mkvmerge, or ``None`` if unavailable."""
    if not has_tool("mkvmerge"):
        return None
    result = run([resolve_tool("mkvmerge"), "--version"], timeout=30.0)
    if not result.ok:
        return None
    match = _MKVMERGE_VERSION_RE.search(result.stdout)
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2) or 0)


def supports_modern_flag_syntax(version: tuple[int, int] | None) -> bool:
    return version is not None and version[0] >= MODERN_FLAG_SYNTAX_MIN_VERSION


def probe_with_mkvmerge(path: Path) -> MediaInfo:
    result = run([resolve_tool("mkvmerge"), "-J", str(path)], timeout=PROBE_TIMEOUT)
    # Exit code 1 is "warnings but output is valid"; only 2+ is a hard failure.
    if result.returncode >= 2:
        raise ProbeError(f"mkvmerge -J failed for {path}: {result.tail()}")
    return parse_mkvmerge_json(path, result.stdout)


def parse_mkvmerge_json(path: Path, payload: str) -> MediaInfo:
    data = load_json_object(path, payload)

    container = data.get("container") or {}
    if container.get("supported") is False:
        raise ProbeError(f"mkvmerge does not support this container: {path}")

    tracks: list[Track] = []
    for raw in data.get("tracks") or []:
        kind = raw.get("type")
        if kind not in ("video", "audio", "subtitles"):
            continue
        props: dict[str, Any] = raw.get("properties") or {}
        tracks.append(
            Track(
                index=int(raw.get("id", len(tracks))),
                kind=kind,
                codec_id=str(props.get("codec_id") or raw.get("codec") or ""),
                language=str(props.get("language") or UNDETERMINED),
                name=props.get("track_name") or None,
                default=bool(props.get("default_track", False)),
                forced=bool(props.get("forced_track", False)),
                hearing_impaired=bool(props.get("flag_hearing_impaired", False)),
            )
        )

    return MediaInfo(
        path=path,
        container=str(container.get("type") or "unknown"),
        tracks=tuple(tracks),
    )
