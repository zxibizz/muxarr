"""Find sidecar audio/subtitle files next to a downloaded video.

Release folders name their track directories arbitrarily -- ``Subs/``, but equally
``RUS Sound [TO Dublyajnaya]`` or ``Надписи``. So rather than an allowlist of
known names, every subdirectory two levels deep is scanned except an explicit
deny-list of folders that hold unrelated media.

The guard against pulling in another release's tracks is the episode marker: in a
folder holding several videos, a sidecar must carry a matching ``SxxEyy``.

The source folder is only ever read. Nothing here opens a file for writing.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from muxarr import language
from muxarr.models import (
    AUDIO_EXTENSIONS,
    SUBTITLE_EXTENSIONS,
    VIDEO_EXTENSIONS,
    ExternalTrack,
    TrackKind,
)

log = logging.getLogger(__name__)

# Folders that contain media which is never part of the main video.
EXCLUDED_DIR_NAMES = frozenset(
    {
        "artwork",
        "bdmv",
        "certificate",
        "covers",
        "extra",
        "extras",
        "featurette",
        "featurettes",
        "proof",
        "sample",
        "samples",
        "scans",
        "screens",
        "screenshot",
        "screenshots",
        "trailer",
        "trailers",
    }
)

MAX_SCAN_DEPTH = 2

# Matches S01E02 and multi-episode runs like S01E02E03 / S01E02-E03.
_SXXEYY_RE = re.compile(r"s(?P<season>\d{1,3})(?P<episodes>(?:[._\- ]?e\d{1,4})+)", re.IGNORECASE)
_EPISODE_RE = re.compile(r"e(\d{1,4})", re.IGNORECASE)
_NxNN_RE = re.compile(r"(?<!\d)(?P<season>\d{1,2})x(?P<episode>\d{1,3})(?!\d)", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class EpisodeRef:
    """Which episode(s) an import is for. Movies use ``None``."""

    season: int
    episodes: tuple[int, ...]


def discover(
    video_path: Path,
    *,
    episode: EpisodeRef | None = None,
) -> list[ExternalTrack]:
    """Collect sidecar tracks that belong to ``video_path``."""
    root = video_path.parent
    if not root.is_dir():
        return []

    sibling_video_count = _count_videos(root)

    tracks: list[ExternalTrack] = []
    for path, context in sorted(_index_candidates(root)):
        if path == video_path:
            continue
        if not _belongs_to(path, episode=episode, sibling_video_count=sibling_video_count):
            continue
        track = _to_external_track(path, video_stem=video_path.stem, context=context)
        if track is not None:
            tracks.append(track)
    return tracks


def _index_candidates(root: Path) -> list[tuple[Path, tuple[str, ...]]]:
    """Every file within :data:`MAX_SCAN_DEPTH`, paired with its folder names.

    Folder names are returned nearest-first, since they are what carries the
    language for multi-dub releases.
    """
    candidates: list[tuple[Path, tuple[str, ...]]] = [(p, ()) for p in _files_in(root)]

    for child in _dirs_in(root):
        if _is_excluded(child.name):
            continue
        candidates += [(p, (child.name,)) for p in _files_in(child)]

        for grandchild in _dirs_in(child):
            if _is_excluded(grandchild.name):
                continue
            candidates += [
                (p, (grandchild.name, child.name)) for p in _files_in(grandchild)
            ]

    return candidates


def _is_excluded(name: str) -> bool:
    return name.lower().strip() in EXCLUDED_DIR_NAMES


def _files_in(directory: Path) -> list[Path]:
    try:
        return [p for p in directory.iterdir() if p.is_file() and not p.name.startswith(".")]
    except OSError as exc:
        log.warning("could not list %s: %s", directory, exc)
        return []


def _dirs_in(directory: Path) -> list[Path]:
    try:
        return [p for p in directory.iterdir() if p.is_dir()]
    except OSError as exc:
        log.warning("could not list %s: %s", directory, exc)
        return []


def _count_videos(root: Path) -> int:
    return sum(1 for p in _files_in(root) if p.suffix.lower() in VIDEO_EXTENSIONS)


def _to_external_track(
    path: Path,
    *,
    video_stem: str,
    context: tuple[str, ...] = (),
) -> ExternalTrack | None:
    suffix = path.suffix.lower()
    kind: TrackKind
    companion: Path | None = None

    if suffix in AUDIO_EXTENSIONS:
        kind = "audio"
    elif suffix in SUBTITLE_EXTENSIONS:
        kind = "subtitles"
        if suffix == ".sub":
            # A bare .sub is an unusable VobSub half; the .idx entry covers the pair.
            return None
        if suffix == ".idx":
            companion = path.with_suffix(".sub")
            if not companion.is_file():
                log.debug("skipping %s: no matching .sub", path)
                return None
    else:
        return None

    attrs = language.infer(path, video_stem=video_stem, context=context)
    return ExternalTrack(
        path=path,
        kind=kind,
        language=attrs.language,
        name=attrs.title,
        forced=attrs.forced,
        hearing_impaired=attrs.hearing_impaired,
        variant=attrs.variant,
        companion=companion,
    )


def _belongs_to(
    path: Path,
    *,
    episode: EpisodeRef | None,
    sibling_video_count: int,
) -> bool:
    """Decide whether a sidecar is for this import.

    A sidecar carrying no episode marker is only accepted when the folder holds a
    single video; in a season pack it is ambiguous and gets dropped rather than
    attached to an arbitrary episode.
    """
    if episode is None:
        return True

    marker = parse_episode_marker(path.name)
    if marker is None:
        return sibling_video_count <= 1

    return marker.season == episode.season and bool(
        set(marker.episodes) & set(episode.episodes)
    )


def parse_episode_marker(name: str) -> EpisodeRef | None:
    """Extract ``S01E02``/``S01E02E03``/``1x02`` from a filename."""
    match = _SXXEYY_RE.search(name)
    if match is not None:
        episodes = tuple(int(e) for e in _EPISODE_RE.findall(match.group("episodes")))
        return EpisodeRef(season=int(match.group("season")), episodes=episodes)

    alt = _NxNN_RE.search(name)
    if alt is not None:
        return EpisodeRef(season=int(alt.group("season")), episodes=(int(alt.group("episode")),))

    return None
