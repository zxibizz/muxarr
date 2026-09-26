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

from dataclasses import replace
from pathlib import Path

from src.application.interfaces.prober import MediaProber
from src.core.logging import get_logger
from src.domain import language
from src.domain.codecs import (
    AUDIO_EXTENSIONS,
    SUBTITLE_EXTENSIONS,
    TAGGED_SIDECAR_SUFFIXES,
    VIDEO_EXTENSIONS,
)
from src.domain.enums import UNDETERMINED, LogComponent, TrackKind
from src.domain.errors import MuxarrError
from src.domain.media import ExternalTrack, Track
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
    prober: MediaProber | None = None,
) -> list[ExternalTrack]:
    """Collect sidecar tracks that belong to ``video_path``."""
    root = video_path.parent
    if not root.is_dir():
        return []

    sibling_video_count = count_videos(root)
    log.bind(folder=root, videos=sibling_video_count, episode=episode).debug(
        "scanning the release folder for sidecars"
    )

    tracks: list[ExternalTrack] = []
    for path, context in sorted(index_candidates(root)):
        if path == video_path:
            continue
        if not belongs_to(path, episode=episode, sibling_video_count=sibling_video_count):
            log.bind(file=path.name).debug("ignoring a file that belongs to another episode")
            continue
        track = _to_external_track(path, video_stem=video_path.stem, context=context, prober=prober)
        if track is None:
            log.bind(file=path.name).debug("ignoring a file that is not an embeddable track")
            continue
        origin = "its own tags" if track.source == "tags" else "filenames"
        log.bind(
            file=track.path.name,
            language=track.language,
            title=track.name,
            folders="/".join(context),
        ).debug(f"{origin} suggest {track.kind} in {track.language}")
        tracks.append(track)
    return tracks


def index_candidates(root: Path) -> list[tuple[Path, tuple[str, ...]]]:
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


def count_videos(root: Path) -> int:
    return sum(1 for p in _files_in(root) if p.suffix.lower() in VIDEO_EXTENSIONS)


def classify(path: Path) -> tuple[TrackKind, Path | None] | None:
    """Decide what kind of track a sidecar is, from its extension alone.

    Returns the kind and, for VobSub, the companion ``.sub`` that travels with the
    ``.idx``. ``None`` means the file is not usable as an external track.
    """
    suffix = path.suffix.lower()

    if suffix in AUDIO_EXTENSIONS:
        return "audio", None
    if suffix not in SUBTITLE_EXTENSIONS:
        return None
    if suffix == ".sub":
        # A bare .sub is an unusable VobSub half; the .idx entry covers the pair.
        return None
    if suffix == ".idx":
        companion = path.with_suffix(".sub")
        if not companion.is_file():
            log.debug("skipping VobSub index with no matching .sub", path=path)
            return None
        return "subtitles", companion
    return "subtitles", None


def _to_external_track(
    path: Path,
    *,
    video_stem: str,
    context: tuple[str, ...] = (),
    prober: MediaProber | None = None,
) -> ExternalTrack | None:
    classified = classify(path)
    if classified is None:
        return None
    kind, companion = classified

    attrs = language.infer(path, video_stem=video_stem, context=context)
    track = ExternalTrack(
        path=path,
        kind=kind,
        language=attrs.language,
        name=attrs.title,
        forced=attrs.forced,
        hearing_impaired=attrs.hearing_impaired,
        variant=attrs.variant,
        companion=companion,
    )
    if attrs.language != UNDETERMINED or prober is None:
        return track

    tagged = embedded_track(path, kind, prober)
    code = language.normalise_language(tagged.language) if tagged else None
    if tagged is None or code is None or code == UNDETERMINED:
        return track

    forced = attrs.forced or tagged.forced
    hearing_impaired = attrs.hearing_impaired or tagged.hearing_impaired
    log.bind(file=path.name, language=code).debug(f"the file's own tags say {code}")
    return replace(
        track,
        language=code,
        name=language.build_title(
            code,
            forced=forced,
            hearing_impaired=hearing_impaired,
            signs=attrs.signs,
            variant=attrs.variant,
        ),
        forced=forced,
        hearing_impaired=hearing_impaired,
        source="tags",
    )


def embedded_track(path: Path, kind: TrackKind, prober: MediaProber) -> Track | None:
    """The track a tag-carrying sidecar declares, or ``None`` if it declares nothing."""
    if path.suffix.lower() not in TAGGED_SIDECAR_SUFFIXES:
        return None
    try:
        info = prober.probe(path)
    except MuxarrError as exc:
        log.bind(file=path.name, error=str(exc)).debug("could not read the sidecar's own tags")
        return None
    candidates = info.of_kind(kind) or info.tracks
    return candidates[0] if candidates else None


class FilesystemTrackDiscovery:
    """Adapter object for the container; delegates to :func:`discover`."""

    def __init__(self, *, prober: MediaProber | None = None) -> None:
        self._prober = prober

    def discover(
        self, video_path: Path, *, episode: EpisodeRef | None = None
    ) -> list[ExternalTrack]:
        return discover(video_path, episode=episode, prober=self._prober)
