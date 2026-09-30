"""Find sidecar audio/subtitle files next to a downloaded video.

Release folders name their track directories arbitrarily -- ``Subs/``, but equally
``RUS Sound [TO Dublyajnaya]`` or ``Надписи``. So rather than an allowlist of
known names, every subdirectory two levels deep is scanned except an explicit
deny-list of folders that hold unrelated media.

The guard against pulling in another release's tracks is the episode marker: in a
folder holding several videos, a sidecar must carry a matching ``SxxEyy``.

All of that assumes the video has a folder of its own. A single-file torrent does
not: it lands in the download directory itself, next to every other download, and
being a single file it has no sidecars. A folder that turns out to hold another
release's video is treated as exactly that, and nothing is taken from it.

The source folder is only ever read. Nothing here opens a file for writing.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
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
from src.domain.journal import LogStage
from src.domain.media import ExternalTrack, Track
from src.domain.naming import EpisodeRef, belongs_to, same_release

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


@dataclass(frozen=True, slots=True)
class ReleaseFolder:
    """The folder a video's sidecars are looked for in, and what counts in it."""

    root: Path
    # Every file that may be one of the video's sidecars, with its folder names.
    candidates: tuple[tuple[Path, tuple[str, ...]], ...]
    # The videos directly in root that are part of the same release, itself included.
    videos: tuple[Path, ...]
    # Another download's video, when root is a download directory rather than a
    # folder of the video's own.
    stranger: Path | None = None


def release_folder(video_path: Path) -> ReleaseFolder | None:
    """Where ``video_path``'s sidecars can be, or ``None`` if its folder is gone.

    Beside another release's video, the video is a single-file download: nothing
    around it is its own.
    """
    root = video_path.parent
    if not root.is_dir():
        return None

    indexed = sorted(index_candidates(root))
    stranger = next(
        (
            path
            for path, _context in indexed
            if _is_video(path) and not same_release(video_path.stem, path.stem)
        ),
        None,
    )
    if stranger is not None:
        return ReleaseFolder(root, (), (video_path,), stranger)

    videos = tuple(path for path, context in indexed if not context and _is_video(path))
    return ReleaseFolder(root, tuple(indexed), videos)


def discover(
    video_path: Path,
    *,
    episode: EpisodeRef | None = None,
    prober: MediaProber | None = None,
) -> list[ExternalTrack]:
    """Collect sidecar tracks that belong to ``video_path``."""
    folder = release_folder(video_path)
    if folder is None:
        return []

    if folder.stranger is not None:
        log.bind(
            stage=LogStage.DISCOVERY.value,
            folder=folder.root,
            other_download=folder.stranger.relative_to(folder.root).as_posix(),
        ).info(
            "the source shares its folder with other downloads, so it is a single-file "
            "download with no sidecars"
        )
    log.bind(folder=folder.root, videos=len(folder.videos), episode=episode).debug(
        "scanning the release folder for sidecars"
    )

    tracks: list[ExternalTrack] = []
    for path, context in folder.candidates:
        if path == video_path:
            continue
        if not belongs_to(path, episode=episode, sibling_video_count=len(folder.videos)):
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


def _is_video(path: Path) -> bool:
    return path.suffix.lower() in VIDEO_EXTENSIONS


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
