"""Codec identity: the suffix and codec-id tables, and the folding rule.

Separate from :mod:`src.domain.media` because discovery needs the extension
allowlists without needing the value objects.
"""

from __future__ import annotations

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
