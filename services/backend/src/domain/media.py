"""Core value objects.

Deliberately plain dataclasses rather than pydantic models: the domain layer
must stay importable without FastAPI or SQLAlchemy present.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from src.domain.codecs import AUDIO_EXTENSIONS, SUBTITLE_EXTENSIONS, normalise_codec
from src.domain.enums import UNDETERMINED, TrackKind


@dataclass(frozen=True, slots=True)
class Track:
    """A track already present inside a container."""

    index: int
    kind: TrackKind
    codec_id: str
    language: str = UNDETERMINED
    name: str | None = None
    default: bool = False
    forced: bool = False
    hearing_impaired: bool = False

    @property
    def codec_family(self) -> str:
        """Coarse codec identity used for de-duplication.

        Normalises the several spellings a codec picks up across containers
        (``A_AC3`` / ``ac3`` / ``AC-3``) onto one token.
        """
        return normalise_codec(self.codec_id)


@dataclass(frozen=True, slots=True)
class MediaInfo:
    """Result of probing a container."""

    path: Path
    container: str
    tracks: tuple[Track, ...]

    def of_kind(self, kind: TrackKind) -> tuple[Track, ...]:
        return tuple(t for t in self.tracks if t.kind == kind)

    @property
    def video(self) -> tuple[Track, ...]:
        return self.of_kind("video")

    @property
    def audio(self) -> tuple[Track, ...]:
        return self.of_kind("audio")

    @property
    def subtitles(self) -> tuple[Track, ...]:
        return self.of_kind("subtitles")


@dataclass(frozen=True, slots=True)
class ExternalTrack:
    """A sidecar file that is a candidate for embedding."""

    path: Path
    kind: TrackKind
    language: str = UNDETERMINED
    name: str | None = None
    forced: bool = False
    hearing_impaired: bool = False
    # Release-group tag ("RHS", "Dublyajnaya") that distinguishes same-language dubs.
    variant: str | None = None
    # VobSub ships as a .sub/.idx pair; mkvmerge is handed the .idx and reads both.
    companion: Path | None = None

    @property
    def codec_family(self) -> str:
        suffix = self.path.suffix.lower()
        mapped = AUDIO_EXTENSIONS.get(suffix) or SUBTITLE_EXTENSIONS.get(suffix)
        return mapped or normalise_codec(suffix)

    def with_language(self, language: str) -> ExternalTrack:
        return replace(self, language=language)
