"""Core value objects.

Deliberately plain dataclasses rather than pydantic models: the core must stay
importable without the ``server`` extra installed.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

TrackKind = Literal["video", "audio", "subtitles"]

UNDETERMINED = "und"


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
    # VobSub ships as a .sub/.idx pair; mkvmerge is handed the .idx and reads both.
    companion: Path | None = None

    @property
    def codec_family(self) -> str:
        suffix = self.path.suffix.lower()
        mapped = AUDIO_EXTENSIONS.get(suffix) or SUBTITLE_EXTENSIONS.get(suffix)
        return mapped or normalise_codec(suffix)

    def with_language(self, language: str) -> ExternalTrack:
        return replace(self, language=language)


# Suffix -> codec family. Also doubles as the extension allowlist for discovery.
AUDIO_EXTENSIONS: dict[str, str] = {
    ".aac": "aac",
    ".ac3": "ac3",
    ".dts": "dts",
    ".dtshd": "dts",
    ".eac3": "eac3",
    ".flac": "flac",
    ".m4a": "aac",
    ".mka": "matroska",
    ".mp3": "mp3",
    ".opus": "opus",
    ".thd": "truehd",
    ".truehd": "truehd",
}

SUBTITLE_EXTENSIONS: dict[str, str] = {
    ".ass": "ass",
    ".idx": "vobsub",
    ".srt": "srt",
    ".ssa": "ass",
    ".sub": "vobsub",
    ".sup": "pgs",
    ".vtt": "webvtt",
}

# Image-based subtitles cannot be converted to text and are rejected by MP4.
IMAGE_SUBTITLE_FAMILIES = frozenset({"vobsub", "pgs"})

# Used to recognise (and skip) other video files while scanning a download folder.
VIDEO_EXTENSIONS = frozenset(
    {
        ".avi",
        ".m4v",
        ".mkv",
        ".mov",
        ".mp4",
        ".mpeg",
        ".mpg",
        ".ts",
        ".webm",
        ".wmv",
    }
)

_CODEC_ID_ALIASES: dict[str, str] = {
    "a_aac": "aac",
    "a_ac3": "ac3",
    "a_dts": "dts",
    "a_eac3": "eac3",
    "a_flac": "flac",
    "a_mpeg/l3": "mp3",
    "a_opus": "opus",
    "a_truehd": "truehd",
    "a_vorbis": "vorbis",
    "ac-3": "ac3",
    "e-ac-3": "eac3",
    "mp4a": "aac",
    "s_dvbsub": "dvbsub",
    "s_hdmv/pgs": "pgs",
    "s_text/ass": "ass",
    "s_text/ssa": "ass",
    "s_text/utf8": "srt",
    "s_text/webvtt": "webvtt",
    "s_vobsub": "vobsub",
    "subrip": "srt",
    "v_mpeg4/iso/avc": "h264",
    "v_mpegh/iso/hevc": "h265",
    "hdmv_pgs_subtitle": "pgs",
    "dvd_subtitle": "vobsub",
}


def normalise_codec(raw: str) -> str:
    """Fold a codec id / file extension onto a stable family token."""
    key = raw.strip().lower().lstrip(".")
    if key in _CODEC_ID_ALIASES:
        return _CODEC_ID_ALIASES[key]
    # mkvmerge ids look like "A_AC3"; strip the type prefix and retry.
    if len(key) > 2 and key[1] == "_":
        stripped = key[2:]
        return _CODEC_ID_ALIASES.get(stripped, stripped)
    return key
