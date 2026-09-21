"""Release-name parsing: which episode(s) a filename refers to.

Pure string work, deliberately separate from the directory scan in
``src.infrastructure.filesystem.track_discovery`` that consumes it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# Matches S01E02 and multi-episode runs like S01E02E03 / S01E02-E03.
_SXXEYY_RE = re.compile(r"s(?P<season>\d{1,3})(?P<episodes>(?:[._\- ]?e\d{1,4})+)", re.IGNORECASE)
_EPISODE_RE = re.compile(r"e(\d{1,4})", re.IGNORECASE)
_NxNN_RE = re.compile(r"(?<!\d)(?P<season>\d{1,2})x(?P<episode>\d{1,3})(?!\d)", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class EpisodeRef:
    """Which episode(s) an import is for. Movies use ``None``."""

    season: int
    episodes: tuple[int, ...]


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


def belongs_to(
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

    return marker.season == episode.season and bool(set(marker.episodes) & set(episode.episodes))
