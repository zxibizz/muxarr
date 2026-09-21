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

from pathlib import Path

from src.core.logging import get_logger
from src.domain import language
from src.domain.codecs import AUDIO_EXTENSIONS, SUBTITLE_EXTENSIONS, VIDEO_EXTENSIONS
from src.domain.enums import LogComponent, TrackKind
from src.domain.media import ExternalTrack
from src.domain.naming import EpisodeRef, belongs_to

log = get_logger(LogComponent.INFRA_DISCOVERY)

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
        if not belongs_to(path, episode=episode, sibling_video_count=sibling_video_count):
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
            candidates += [(p, (grandchild.name, child.name)) for p in _files_in(grandchild)]

    return candidates


def _is_excluded(name: str) -> bool:
    return name.lower().strip() in EXCLUDED_DIR_NAMES


def _files_in(directory: Path) -> list[Path]:
    try:
        return [p for p in directory.iterdir() if p.is_file() and not p.name.startswith(".")]
    except OSError as exc:
        log.warning("could not list directory", path=directory, error=str(exc))
        return []


def _dirs_in(directory: Path) -> list[Path]:
    try:
        return [p for p in directory.iterdir() if p.is_dir()]
    except OSError as exc:
        log.warning("could not list directory", path=directory, error=str(exc))
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
                log.debug("skipping VobSub index with no matching .sub", path=path)
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


class FilesystemTrackDiscovery:
    """Adapter object for the container; delegates to :func:`discover`."""

    def discover(
        self, video_path: Path, *, episode: EpisodeRef | None = None
    ) -> list[ExternalTrack]:
        return discover(video_path, episode=episode)
