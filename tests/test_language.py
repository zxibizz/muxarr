from __future__ import annotations

from pathlib import Path

import pytest

from muxarr.language import build_title, infer, normalise_language, tokenise


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("Movie.2024.1080p.eng.srt", "eng"),
        ("Movie.2024.1080p.ru.forced.srt", "rus"),
        ("2_English.srt", "eng"),
        ("3_English.SDH.srt", "eng"),
        ("Movie.2024.German.ac3", "ger"),
        ("Movie.2024.deu.ac3", "ger"),
        ("subs/French.srt", "fre"),
        ("Movie.pt-BR.srt", "por"),
        ("Movie.2024.srt", "und"),
    ],
)
def test_language_inference(filename: str, expected: str) -> None:
    assert infer(Path(filename)).language == expected


def test_rightmost_language_token_wins() -> None:
    """A language word inside the title must not beat the real tag."""
    assert infer(Path("The.English.Patient.1996.rus.srt")).language == "rus"


def test_video_stem_is_stripped_before_tokenising() -> None:
    video_stem = "Spanish.Harlem.2024.1080p"
    attrs = infer(Path(f"{video_stem}.eng.srt"), video_stem=video_stem)
    assert attrs.language == "eng"


def test_hi_token_is_hearing_impaired_not_hindi() -> None:
    attrs = infer(Path("Movie.2024.eng.hi.srt"))
    assert attrs.language == "eng"
    assert attrs.hearing_impaired is True


@pytest.mark.parametrize(
    ("filename", "forced", "sdh"),
    [
        ("Movie.eng.forced.srt", True, False),
        ("Movie.eng.sdh.srt", False, True),
        ("Movie.eng.cc.srt", False, True),
        ("Movie.eng.Foreign.Parts.Only.srt", True, False),
        ("Movie.eng.srt", False, False),
    ],
)
def test_flag_inference(filename: str, forced: bool, sdh: bool) -> None:
    attrs = infer(Path(filename))
    assert (attrs.forced, attrs.hearing_impaired) == (forced, sdh)


def test_tokenise_splits_on_any_separator() -> None:
    assert tokenise("Movie.2024_1080p-eng [x264]") == [
        "movie",
        "2024",
        "1080p",
        "eng",
        "x264",
    ]


def test_normalise_language_rejects_non_languages() -> None:
    assert normalise_language("1080p") is None
    assert normalise_language("ENG") == "eng"


def test_build_title() -> None:
    assert build_title("eng", forced=True, hearing_impaired=False) == "English (Forced)"
    assert build_title("eng", forced=False, hearing_impaired=False) == "English"
    assert build_title("und", forced=False, hearing_impaired=False) is None
