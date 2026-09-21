"""Container inspection.

``mkvmerge -J`` is preferred because it reports exactly the properties muxarr
sets back (``forced_track``, ``flag_hearing_impaired``) and because a file it
cannot parse is a file it cannot mux either. ``ffprobe`` is the fallback for the
odd container mkvmerge refuses.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from muxarr.errors import ProbeError
from muxarr.models import UNDETERMINED, MediaInfo, Track, TrackKind
from muxarr.proc import has_tool, resolve_tool, run

log = logging.getLogger(__name__)

PROBE_TIMEOUT = 120.0

_MKVMERGE_VERSION_RE = re.compile(r"\bv(\d+)(?:\.(\d+))?")

# mkvtoolnix 58 renamed the flag options; older releases only accept the short forms.
MODERN_FLAG_SYNTAX_MIN_VERSION = 58

_FFPROBE_KIND: dict[str, TrackKind] = {
    "video": "video",
    "audio": "audio",
    "subtitle": "subtitles",
}


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


def probe(path: Path) -> MediaInfo:
    """Inspect a container, preferring mkvmerge and falling back to ffprobe."""
    if not path.is_file():
        raise ProbeError(f"not a file: {path}")

    if has_tool("mkvmerge"):
        try:
            return probe_with_mkvmerge(path)
        except ProbeError as exc:
            log.debug("mkvmerge could not probe %s (%s); trying ffprobe", path, exc)

    if has_tool("ffprobe"):
        return probe_with_ffprobe(path)

    raise ProbeError(f"no usable probe backend for {path}: install mkvtoolnix or ffmpeg")


def probe_with_mkvmerge(path: Path) -> MediaInfo:
    result = run([resolve_tool("mkvmerge"), "-J", str(path)], timeout=PROBE_TIMEOUT)
    # Exit code 1 is "warnings but output is valid"; only 2+ is a hard failure.
    if result.returncode >= 2:
        raise ProbeError(f"mkvmerge -J failed for {path}: {result.tail()}")
    return parse_mkvmerge_json(path, result.stdout)


def parse_mkvmerge_json(path: Path, payload: str) -> MediaInfo:
    data = _load_json(path, payload)

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
    data = _load_json(path, payload)

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


def _load_json(path: Path, payload: str) -> dict[str, Any]:
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ProbeError(f"probe output for {path} was not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ProbeError(f"probe output for {path} was not a JSON object")
    return parsed
