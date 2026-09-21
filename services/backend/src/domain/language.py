"""Infer language and track flags from a sidecar filename.

Release naming is not standardised, so this is heuristic by design. The rules were
chosen to match what actually turns up in download folders:

    Movie.2024.1080p.eng.srt                -> eng
    Movie.2024.1080p.ru.forced.srt          -> rus, forced
    Subs/2_English.srt                      -> eng
    Subs/3_English.SDH.srt                  -> eng, hearing impaired
    RUS Sound [Dublyajnaya]/Show.S01E01.mka -> rus, variant "Dublyajnaya"
    Nadpisi/Show.S01E01.ass                 -> signs, forced

When the filename yields nothing, the names of the containing folders are used as
a fallback -- multi-dub releases carry the language on the folder, not the file.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from src.domain.enums import UNDETERMINED

# (ISO 639-2/B code, display name, aliases)
# Aliases include the ISO 639-1 pair and, where they differ, the ISO 639-2/T code,
# because releases use both spellings interchangeably (ger/deu, fre/fra, ...).
_LANGUAGE_TABLE: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("ara", "Arabic", ("ar", "arabic")),
    ("bul", "Bulgarian", ("bg", "bulgarian")),
    ("ces", "Czech", ("cs", "cze", "czech")),
    ("chi", "Chinese", ("zh", "zho", "chinese", "mandarin", "cantonese")),
    ("dan", "Danish", ("da", "danish")),
    ("dut", "Dutch", ("nl", "nld", "dutch", "flemish")),
    ("eng", "English", ("en", "english", "англ", "английский")),
    ("est", "Estonian", ("et", "estonian")),
    ("fin", "Finnish", ("fi", "finnish")),
    ("fre", "French", ("fr", "fra", "french", "vf", "vff", "truefrench")),
    ("ger", "German", ("de", "deu", "german")),
    ("gre", "Greek", ("el", "ell", "greek")),
    ("heb", "Hebrew", ("he", "iw", "hebrew")),
    # No "hi" alias: it collides with the hearing-impaired tag, which is far more common.
    ("hin", "Hindi", ("hindi",)),
    ("hrv", "Croatian", ("hr", "croatian")),
    ("hun", "Hungarian", ("hu", "hungarian")),
    ("ice", "Icelandic", ("is", "isl", "icelandic")),
    ("ind", "Indonesian", ("id", "indonesian")),
    ("ita", "Italian", ("it", "italian")),
    ("jpn", "Japanese", ("ja", "jp", "japanese", "яп", "японский")),
    ("kor", "Korean", ("ko", "korean")),
    ("lav", "Latvian", ("lv", "latvian")),
    ("lit", "Lithuanian", ("lt", "lithuanian")),
    ("may", "Malay", ("ms", "msa", "malay")),
    ("nob", "Norwegian", ("no", "nor", "nb", "norwegian", "bokmal")),
    ("per", "Persian", ("fa", "fas", "persian", "farsi")),
    ("pol", "Polish", ("pl", "polish")),
    ("por", "Portuguese", ("pt", "portuguese", "brazilian", "ptbr", "pob")),
    ("rum", "Romanian", ("ro", "ron", "romanian")),
    ("rus", "Russian", ("ru", "russian", "рус", "русский", "русская", "дубляж")),
    ("slo", "Slovak", ("sk", "slk", "slovak")),
    ("slv", "Slovenian", ("sl", "slovenian")),
    ("spa", "Spanish", ("es", "spanish", "castellano", "latino", "esla")),
    ("srp", "Serbian", ("sr", "serbian")),
    ("swe", "Swedish", ("sv", "se", "swedish")),
    ("tha", "Thai", ("th", "thai")),
    ("tur", "Turkish", ("tr", "turkish")),
    ("ukr", "Ukrainian", ("uk", "ukrainian", "укр", "украинский")),
    ("vie", "Vietnamese", ("vi", "vietnamese")),
)

_ALIAS_TO_CODE: dict[str, str] = {}
_CODE_TO_NAME: dict[str, str] = {}
for _code, _name, _aliases in _LANGUAGE_TABLE:
    _CODE_TO_NAME[_code] = _name
    _ALIAS_TO_CODE[_code] = _code
    for _alias in _aliases:
        _ALIAS_TO_CODE[_alias] = _code

_FORCED_TOKENS = frozenset({"forced", "forcedsubs"})
_HEARING_IMPAIRED_TOKENS = frozenset({"sdh", "cc", "hi", "hearingimpaired"})
# "Signs & songs" tracks translate on-screen text only, so they behave as forced.
_SIGNS_TOKENS = frozenset({"signs", "songs", "nadpisi", "надписи", "титры"})

# Release-metadata noise that must never be mistaken for a group/variant name.
_NOISE_TOKENS = frozenset(
    {
        "1080p", "2160p", "480p", "576p", "720p", "4k", "8bit", "10bit",
        "aac", "ac3", "avc", "dts", "eac3", "flac", "h264", "h265", "hevc",
        "mp3", "opus", "truehd", "x264", "x265", "xvid",
        "bd", "bdrip", "bluray", "brrip", "dvdrip", "hdtv", "web", "webdl", "webrip",
        "ass", "idx", "mka", "mkv", "srt", "ssa", "sub", "sup",
        "audio", "dub", "sound", "track", "звук", "озвучка",
    }
)

# Unicode-aware: Cyrillic folder names like "Надписи" must survive tokenising.
_SEPARATOR_RE = re.compile(r"[\W_]+", re.UNICODE)
_EPISODE_TOKEN_RE = re.compile(r"^s\d{1,3}e\d{1,4}$|^\d+$", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class SidecarAttributes:
    language: str
    forced: bool
    hearing_impaired: bool
    title: str | None
    signs: bool = False
    variant: str | None = None


def language_name(code: str) -> str | None:
    return _CODE_TO_NAME.get(code)


def normalise_language(raw: str) -> str | None:
    """Map one token to an ISO 639-2/B code, or ``None`` if it isn't a language."""
    return _ALIAS_TO_CODE.get(raw.strip().lower().replace("-", "").replace("_", ""))


def split_tokens(text: str) -> list[str]:
    """Split on any non-alphanumeric run, preserving the original case."""
    return [tok for tok in _SEPARATOR_RE.split(text) if tok]


def strip_video_stem(stem: str, video_stem: str | None) -> str:
    if video_stem and stem.lower().startswith(video_stem.lower()):
        return stem[len(video_stem) :]
    return stem


def tokenise(stem: str, *, video_stem: str | None = None) -> list[str]:
    """Split a filename stem into lowercase alphanumeric tokens.

    When the sidecar is named after the video (``Movie.2024.1080p.eng.srt`` next to
    ``Movie.2024.1080p.mkv``) the shared prefix is stripped first, so title words
    can't be mistaken for language tags.
    """
    return [tok.lower() for tok in split_tokens(strip_video_stem(stem, video_stem))]


def infer(
    path: Path,
    *,
    video_stem: str | None = None,
    context: Sequence[str] = (),
) -> SidecarAttributes:
    """Derive language, flags and variant tag from a sidecar path.

    ``context`` is the enclosing folder names, nearest first. They are consulted
    only when the filename itself is uninformative.
    """
    tokens = tokenise(path.stem, video_stem=video_stem)
    context_tokens = [tok for name in context for tok in tokenise(name)]
    combined = set(tokens) | set(context_tokens)

    signs = bool(_SIGNS_TOKENS & combined)
    forced = (
        signs
        or bool(_FORCED_TOKENS & combined)
        or ("foreign" in combined and "parts" in combined)
    )
    hearing_impaired = bool(_HEARING_IMPAIRED_TOKENS & combined)

    language = _rightmost_language(tokens)
    if language == UNDETERMINED:
        for name in context:
            language = _rightmost_language(tokenise(name))
            if language != UNDETERMINED:
                break

    variant = variant_tag(path, video_stem=video_stem, context=context)

    return SidecarAttributes(
        language=language,
        forced=forced,
        hearing_impaired=hearing_impaired,
        signs=signs,
        variant=variant,
        title=build_title(
            language,
            forced=forced,
            hearing_impaired=hearing_impaired,
            signs=signs,
            variant=variant,
        ),
    )


def _rightmost_language(tokens: list[str]) -> str:
    """Rightmost wins: "The.English.Patient.1996.rus.srt" is Russian, not English."""
    for token in reversed(tokens):
        if token in _FORCED_TOKENS or token in _HEARING_IMPAIRED_TOKENS:
            continue
        code = normalise_language(token)
        if code is not None:
            return code
    return UNDETERMINED


def variant_tag(
    path: Path,
    *,
    video_stem: str | None = None,
    context: Sequence[str] = (),
) -> str | None:
    """The distinguishing group tag, e.g. ``Dublyajnaya`` or ``RHS``.

    This is what keeps two same-language dubs from de-duplicating into one.
    """
    remainder = strip_video_stem(path.stem, video_stem)
    candidates = [tok for tok in split_tokens(remainder) if _is_variant(tok)]
    if candidates:
        return candidates[-1]

    for name in context:
        folder_candidates = [tok for tok in split_tokens(name) if _is_variant(tok)]
        if folder_candidates:
            return folder_candidates[-1]

    return None


def _is_variant(token: str) -> bool:
    lowered = token.lower()
    return (
        lowered not in _NOISE_TOKENS
        and lowered not in _FORCED_TOKENS
        and lowered not in _HEARING_IMPAIRED_TOKENS
        and lowered not in _SIGNS_TOKENS
        and normalise_language(lowered) is None
        and _EPISODE_TOKEN_RE.match(lowered) is None
    )


def build_title(
    language: str,
    *,
    forced: bool,
    hearing_impaired: bool,
    signs: bool = False,
    variant: str | None = None,
) -> str | None:
    """Human-readable track name, e.g. ``"Russian (Dublyajnaya)"``."""
    qualifiers: list[str] = []
    if variant:
        qualifiers.append(variant)
    if signs:
        qualifiers.append("Signs")
    elif forced:
        qualifiers.append("Forced")
    if hearing_impaired:
        qualifiers.append("SDH")

    name = _CODE_TO_NAME.get(language)
    if name is None:
        return ", ".join(qualifiers) if qualifiers else None
    return f"{name} ({', '.join(qualifiers)})" if qualifiers else name
