"""Decide which discovered sidecars are worth embedding.

Selection is conservative: anything already represented inside the container is
dropped, so re-running an import never grows a file without bound.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.domain.codecs import IMAGE_SUBTITLE_FAMILIES
from src.domain.enums import DedupeMode, RejectCode, TrackKind
from src.domain.language import normalise_language
from src.domain.media import ExternalTrack, MediaInfo, Track

_KIND_ORDER: dict[TrackKind, int] = {"video": 0, "audio": 1, "subtitles": 2}

REJECT_REASONS: dict[RejectCode, str] = {
    "image_subtitle": "image-based subtitle excluded by policy",
    "undetermined_language": "language could not be determined",
    "language_not_kept": "language is not in the keep list",
    "already_present": "already present in container",
    "track_limit": "max_external_tracks reached",
    "file_missing": "file disappeared before muxing",
    "file_empty": "file is empty",
    "uninspectable": "the file could not be inspected",
    "no_tracks": "the file holds no track mkvmerge can read",
}


@dataclass(frozen=True, slots=True)
class Rejection:
    track: ExternalTrack
    code: RejectCode
    detail: str = ""

    @property
    def reason(self) -> str:
        base = REJECT_REASONS[self.code]
        return f"{base}: {self.detail}" if self.detail else base


@dataclass(frozen=True, slots=True)
class SelectionPolicy:
    dedupe: DedupeMode = "language_codec"
    max_external_tracks: int = 24
    skip_image_subtitles: bool = False
    skip_undetermined_language: bool = False
    # Empty means every language of that kind is kept.
    keep_audio_languages: frozenset[str] = frozenset()
    keep_subtitle_languages: frozenset[str] = frozenset()

    def keeps(self, kind: TrackKind, language: str) -> bool:
        wanted = self._keep_list(kind)
        return not wanted or canonical_language(language) in wanted

    def prunes(self, kind: TrackKind) -> bool:
        return bool(self._keep_list(kind))

    def _keep_list(self, kind: TrackKind) -> frozenset[str]:
        if kind == "audio":
            return self.keep_audio_languages
        if kind == "subtitles":
            return self.keep_subtitle_languages
        return frozenset()


@dataclass(frozen=True, slots=True)
class Pruning:
    """The source's own tracks split into those that survive the remux and those that don't."""

    kept: MediaInfo
    removed: tuple[Track, ...]

    def __bool__(self) -> bool:
        return bool(self.removed)


def canonical_language(code: str) -> str:
    """One spelling per language, so ``ger`` and ``deu`` compare equal."""
    return normalise_language(code) or code.strip().lower()


def prune(existing: MediaInfo, policy: SelectionPolicy | None = None) -> Pruning:
    """Decide which of the source's audio and subtitle tracks the keep lists drop."""
    policy = policy or SelectionPolicy()
    kept: list[Track] = []
    removed: list[Track] = []
    for track in existing.tracks:
        if policy.keeps(track.kind, track.language):
            kept.append(track)
        else:
            removed.append(track)
    return Pruning(
        kept=MediaInfo(path=existing.path, container=existing.container, tracks=tuple(kept)),
        removed=tuple(removed),
    )


@dataclass(frozen=True, slots=True)
class Selection:
    accepted: tuple[ExternalTrack, ...]
    rejected: tuple[Rejection, ...]

    def __bool__(self) -> bool:
        return bool(self.accepted)


def select(
    existing: MediaInfo,
    candidates: list[ExternalTrack],
    policy: SelectionPolicy | None = None,
) -> Selection:
    """Filter and order ``candidates`` against what ``existing`` already contains."""
    policy = policy or SelectionPolicy()

    seen = {
        _signature(t.kind, t.language, t.codec_family, t.forced, t.hearing_impaired, None, policy)
        for t in existing.tracks
    }

    accepted: list[ExternalTrack] = []
    rejected: list[Rejection] = []

    for candidate in _ordered(candidates):
        code = _policy_rejection(candidate, policy)
        if code is not None:
            rejected.append(Rejection(candidate, code))
            continue

        signature = _signature(
            candidate.kind,
            candidate.language,
            candidate.codec_family,
            candidate.forced,
            candidate.hearing_impaired,
            candidate.variant,
            policy,
        )
        if signature is not None and signature in seen:
            rejected.append(Rejection(candidate, "already_present"))
            continue

        if len(accepted) >= policy.max_external_tracks:
            rejected.append(Rejection(candidate, "track_limit"))
            continue

        accepted.append(candidate)
        if signature is not None:
            seen.add(signature)

    return Selection(accepted=tuple(accepted), rejected=tuple(rejected))


def _policy_rejection(candidate: ExternalTrack, policy: SelectionPolicy) -> RejectCode | None:
    if policy.skip_image_subtitles and candidate.codec_family in IMAGE_SUBTITLE_FAMILIES:
        return "image_subtitle"
    if policy.skip_undetermined_language and candidate.language == "und":
        return "undetermined_language"
    if not policy.keeps(candidate.kind, candidate.language):
        return "language_not_kept"
    return None


def _ordered(candidates: list[ExternalTrack]) -> list[ExternalTrack]:
    """Audio before subtitles, then by language, forced last within a language."""
    return sorted(
        candidates,
        key=lambda t: (
            _KIND_ORDER.get(t.kind, 9),
            t.language,
            t.forced,
            t.hearing_impaired,
            t.path.name,
        ),
    )


def _signature(
    kind: TrackKind,
    language: str,
    codec_family: str,
    forced: bool,
    hearing_impaired: bool,
    variant: str | None,
    policy: SelectionPolicy,
) -> tuple[object, ...] | None:
    """Identity used for de-duplication, or ``None`` when deduping is disabled.

    ``variant`` keeps two different fansub/dub groups from collapsing into one
    track; a sidecar with no group tag still de-duplicates against the container.
    """
    if policy.dedupe == "off":
        return None
    tag = (variant or "").lower()
    if policy.dedupe == "language":
        return (kind, language, forced, hearing_impaired, tag)
    return (kind, language, codec_family, forced, hearing_impaired, tag)
