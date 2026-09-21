"""Infer language and track flags from a sidecar filename.

Release naming is not standardised, so this is heuristic by design. The rules were
chosen to match what actually turns up in download folders:

    Movie.2024.1080p.eng.srt        -> eng
    Movie.2024.1080p.ru.forced.srt  -> rus, forced
    Subs/2_English.srt              -> eng
    Subs/3_English.SDH.srt          -> eng, hearing impaired
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from muxarr.models import UNDETERMINED

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
    ("eng", "English", ("en", "english")),
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
    ("jpn", "Japanese", ("ja", "jp", "japanese")),
    ("kor", "Korean", ("ko", "korean")),
    ("lav", "Latvian", ("lv", "latvian")),
    ("lit", "Lithuanian", ("lt", "lithuanian")),
    ("may", "Malay", ("ms", "msa", "malay")),
    ("nob", "Norwegian", ("no", "nor", "nb", "norwegian", "bokmal")),
    ("per", "Persian", ("fa", "fas", "persian", "farsi")),
    ("pol", "Polish", ("pl", "polish")),
    ("por", "Portuguese", ("pt", "portuguese", "brazilian", "ptbr", "pob")),
    ("rum", "Romanian", ("ro", "ron", "romanian")),
    ("rus", "Russian", ("ru", "russian")),
    ("slo", "Slovak", ("sk", "slk", "slovak")),
    ("slv", "Slovenian", ("sl", "slovenian")),
    ("spa", "Spanish", ("es", "spanish", "castellano", "latino", "esla")),
    ("srp", "Serbian", ("sr", "serbian")),
    ("swe", "Swedish", ("sv", "se", "swedish")),
    ("tha", "Thai", ("th", "thai")),
    ("tur", "Turkish", ("tr", "turkish")),
    ("ukr", "Ukrainian", ("uk", "ukrainian")),
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
_SEPARATOR_RE = re.compile(r"[^0-9a-z]+")


@dataclass(frozen=True, slots=True)
class SidecarAttributes:
    language: str
    forced: bool
    hearing_impaired: bool
    title: str | None


def language_name(code: str) -> str | None:
    return _CODE_TO_NAME.get(code)


def normalise_language(raw: str) -> str | None:
    """Map one token to an ISO 639-2/B code, or ``None`` if it isn't a language."""
    return _ALIAS_TO_CODE.get(raw.strip().lower().replace("-", "").replace("_", ""))


def tokenise(stem: str, *, video_stem: str | None = None) -> list[str]:
    """Split a filename stem into lowercase alphanumeric tokens.

    When the sidecar is named after the video (``Movie.2024.1080p.eng.srt`` next to
    ``Movie.2024.1080p.mkv``) the shared prefix is stripped first, so title words
    can't be mistaken for language tags.
    """
    working = stem
    if video_stem and working.lower().startswith(video_stem.lower()):
        working = working[len(video_stem) :]
    return [tok for tok in _SEPARATOR_RE.split(working.lower()) if tok]


def infer(path: Path, *, video_stem: str | None = None) -> SidecarAttributes:
    """Derive language + flags from a sidecar path."""
    tokens = tokenise(path.stem, video_stem=video_stem)

    forced = bool(_FORCED_TOKENS & set(tokens)) or ("foreign" in tokens and "parts" in tokens)
    hearing_impaired = bool(_HEARING_IMPAIRED_TOKENS & set(tokens))

    # Rightmost wins: "The.English.Patient.1996.rus.srt" is Russian, not English.
    language = UNDETERMINED
    for token in reversed(tokens):
        if token in _FORCED_TOKENS or token in _HEARING_IMPAIRED_TOKENS:
            continue
        code = normalise_language(token)
        if code is not None:
            language = code
            break

    return SidecarAttributes(
        language=language,
        forced=forced,
        hearing_impaired=hearing_impaired,
        title=build_title(language, forced=forced, hearing_impaired=hearing_impaired),
    )


def build_title(language: str, *, forced: bool, hearing_impaired: bool) -> str | None:
    """Human-readable track name, e.g. ``"English (Forced)"``."""
    name = _CODE_TO_NAME.get(language)
    if name is None:
        return None
    qualifiers = [q for q, on in (("Forced", forced), ("SDH", hearing_impaired)) if on]
    return f"{name} ({', '.join(qualifiers)})" if qualifiers else name
