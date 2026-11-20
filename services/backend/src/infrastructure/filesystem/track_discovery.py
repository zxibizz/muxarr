"""Find sidecar audio/subtitle files next to a downloaded video.

Release folders name their track directories arbitrarily -- ``Subs/``, but equally
``RUS Sound [TO Dublyajnaya]`` or ``Надписи``. So rather than an allowlist of
known names, every subdirectory two levels deep is scanned except an explicit
deny-list of folders that hold unrelated media.

The guard against pulling in another release's tracks is the episode marker: in a
folder holding several videos, a sidecar must carry a matching ``SxxEyy``.

All of that assumes the video has a folder of its own. A single-file torrent does
not: it lands in the download directory itself, next to every other download, and
being a single file it has no sidecars. A pack, on the other hand, may ship videos
named nothing like its episodes -- disc menus, bonus clips, creditless openings --
in folders named anything at all. Either way the folder holds videos of other
releases; what tells the two apart is the folder's own name. A release folder is
named after its release, a download directory (``downloads``, ``tv-sonarr``) is
not:

* in a folder named after the release, a top-level folder holding another
  release's video is that video's and is skipped, apart from files naming an
  episode or one of the release's videos -- a dub folder may hold a stray clip;
  everything else is searched as usual, and the AI provider is shown the other
  videos. A file named after one of those videos is never a candidate;
* in any other folder, nothing loose is taken, nothing from a top-level folder
  holding a video, and of the rest only what is named after the video
  (``RUS Sound/<video>.mka``); the AI provider is not asked, since the listing
  would be other downloads'.

The source folder is only ever read. Nothing here opens a file for writing.
"""

from __future__ import annotations

import re
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
from src.domain.naming import (
    EpisodeRef,
    belongs_to,
    named_after,
    names_release,
    parse_episode_marker,
    same_release,
)

log = get_logger(LogComponent.INFRA_DISCOVERY)

# Folders that contain media which is never part of the main video. Disc menus
# and bonus clips matter beyond that: they are videos named unlike the release,
# so scanned they would pass for another download and hide every sidecar.
EXCLUDED_DIR_NAMES = frozenset(
    {
        "artwork",
        "bd menu",
        "bd menus",
        "bdmenu",
        "bdmv",
        "bonus",
        "bonuses",
        "certificate",
        "covers",
        "extra",
        "extras",
        "featurette",
        "featurettes",
        "menu",
        "menus",
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
    # Videos of other releases under root: another download's when root is a
    # download directory, or the pack's own menus and bonus clips.
    foreign: tuple[Path, ...] = ()
    # Whether root is named after the video's release, and so is its folder.
    own: bool = True
    # The videos directly in root that a sidecar without an episode marker could
    # be for: the release's own and any loose menu or bonus clip.
    loose_videos: int = 0

    @property
    def ambiguous(self) -> bool:
        """Whether root may be a download directory rather than the video's folder."""
        return bool(self.foreign) and not self.own


def release_folder(video_path: Path) -> ReleaseFolder | None:
    """Where ``video_path``'s sidecars can be, or ``None`` if its folder is gone.

    Beside videos of other releases, a top-level folder holding one is that
    video's, apart from files naming an episode or a video of the release; when
    root is not even named after the release, every folder holding a video is
    another download's, whole, and so is every loose file.
    """
    root = video_path.parent
    if not root.is_dir():
        return None

    indexed = sorted(index_candidates(root))
    foreign = frozenset(
        path
        for path, _context in indexed
        if _is_video(path) and not same_release(video_path.stem, path.stem)
    )
    videos = tuple(
        path for path, context in indexed if not context and _is_video(path) and path not in foreign
    )
    if not foreign:
        return ReleaseFolder(root, tuple(indexed), videos, loose_videos=len(videos))

    own = names_release(root.name, video_path.stem)
    holders = foreign if own else {path for path, _context in indexed if _is_video(path)}
    # context is nearest-first, so its last entry is the folder directly under root.
    taken = {root / context[-1] for path, context in indexed if context and path in holders}
    ours = [path.stem for path, _context in indexed if _is_video(path) and path not in foreign]

    def admitted(path: Path, context: tuple[str, ...]) -> bool:
        if any(named_after(path.name, other.stem) for other in foreign):
            return False
        if not context:
            return own or path == video_path
        if not _within(path, taken):
            return True
        # A release's folder holding a menu or a stray clip may still hold its dubs:
        # a file naming its episode or video says whose it is.
        return own and (
            parse_episode_marker(path.name) is not None
            or any(named_after(path.name, stem) for stem in ours)
        )

    candidates = tuple((path, context) for path, context in indexed if admitted(path, context))
    loose = sum(1 for path in foreign if path.parent == root)
    return ReleaseFolder(root, candidates, videos, tuple(sorted(foreign)), own, len(videos) + loose)


def _within(path: Path, folders: set[Path]) -> bool:
    return any(parent in folders for parent in path.parents)


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

    if folder.ambiguous:
        log.bind(
            stage=LogStage.DISCOVERY.value,
            folder=folder.root,
            other_video=folder.foreign[0].relative_to(folder.root).as_posix(),
            other_videos=len(folder.foreign),
        ).info(
            "the folder is not named after the release and holds videos of other "
            "releases, so it may be shared with other downloads: only sidecars named "
            "after the video, in folders without a video, are taken"
        )
    elif folder.foreign:
        log.bind(
            stage=LogStage.DISCOVERY.value,
            folder=folder.root,
            other_video=folder.foreign[0].relative_to(folder.root).as_posix(),
            other_videos=len(folder.foreign),
        ).info(
            "the release folder also holds videos named unlike the release, such as "
            "disc menus or bonus clips; the folders holding them are skipped"
        )
    log.bind(folder=folder.root, videos=len(folder.videos), episode=episode).debug(
        "scanning the release folder for sidecars"
    )

    tracks: list[ExternalTrack] = []
    for path, context in folder.candidates:
        if path == video_path:
            continue
        if folder.ambiguous and not named_after(path.name, video_path.stem):
            continue
        if not belongs_to(
            path,
            episode=episode,
            sibling_video_count=folder.loose_videos,
            video_stem=video_path.stem,
        ):
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
    return _folder_key(name) in EXCLUDED_DIR_NAMES


def _folder_key(name: str) -> str:
    # Packs decorate these folders freely ("BD_Menu", "Bonus [BD]", "[Extras]"),
    # so compare the bare words only.
    lowered = name.lower()
    bare = _FOLDER_TAG_RE.sub(" ", lowered)
    if not bare.strip(" _-."):
        bare = lowered.translate(_BRACKETS)
    return " ".join(_FOLDER_SEPARATOR_RE.sub(" ", bare).split())


_FOLDER_TAG_RE = re.compile(r"\[[^\]]*\]|\([^)]*\)")
_FOLDER_SEPARATOR_RE = re.compile(r"[_\-.]+")
_BRACKETS = str.maketrans("[]()", "    ")


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
