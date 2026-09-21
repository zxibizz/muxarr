"""Decide which discovered sidecars are worth embedding.

Selection is conservative: anything already represented inside the container is
dropped, so re-running an import never grows a file without bound.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.domain.codecs import IMAGE_SUBTITLE_FAMILIES
from src.domain.enums import DedupeMode, TrackKind
from src.domain.media import ExternalTrack, MediaInfo

_KIND_ORDER: dict[TrackKind, int] = {"video": 0, "audio": 1, "subtitles": 2}


@dataclass(frozen=True, slots=True)
class SelectionPolicy:
    dedupe: DedupeMode = "language_codec"
    max_external_tracks: int = 24
    skip_image_subtitles: bool = False
    skip_undetermined_language: bool = False


@dataclass(frozen=True, slots=True)
class Selection:
    accepted: tuple[ExternalTrack, ...]
    rejected: tuple[tuple[ExternalTrack, str], ...]

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
    rejected: list[tuple[ExternalTrack, str]] = []

    for candidate in _ordered(candidates):
        reason = _reject_reason(candidate, policy)
        if reason is not None:
            rejected.append((candidate, reason))
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
            rejected.append((candidate, "already present in container"))
            continue

        if len(accepted) >= policy.max_external_tracks:
            rejected.append((candidate, "max_external_tracks reached"))
            continue

        accepted.append(candidate)
        if signature is not None:
            seen.add(signature)

    return Selection(accepted=tuple(accepted), rejected=tuple(rejected))


def _reject_reason(candidate: ExternalTrack, policy: SelectionPolicy) -> str | None:
    if policy.skip_image_subtitles and candidate.codec_family in IMAGE_SUBTITLE_FAMILIES:
        return "image-based subtitle excluded by policy"
    if policy.skip_undetermined_language and candidate.language == "und":
        return "language could not be determined"
    if not candidate.path.is_file():
        return "file disappeared before muxing"
    if candidate.path.stat().st_size == 0:
        return "file is empty"
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
