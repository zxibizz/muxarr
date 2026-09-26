from __future__ import annotations

from pathlib import Path

from src.infrastructure.ai.excerpt import MAX_EXCERPT_CHARS, MAX_READ_BYTES, excerpt
from tests.conftest import touch

SRT = """\
1
00:00:01,000 --> 00:00:02,000
<i>Привет,</i> {\\an8}как дела?

2
00:00:03,000 --> 00:00:04,000
Всё хорошо.
"""


def test_srt_keeps_only_what_a_viewer_reads(tmp_path: Path) -> None:
    sample = excerpt(touch(tmp_path / "a.srt", SRT))

    assert sample is not None
    assert sample.text == "Привет, как дела? / Всё хорошо."
    assert sample.reliable


def test_webvtt_skips_the_header_notes_and_cue_ids(tmp_path: Path) -> None:
    vtt = (
        "WEBVTT\n\nNOTE written by hand\n\n"
        "intro\n00:01.000 --> 00:02.000 align:start\nBonjour tout le monde\n"
    )

    sample = excerpt(touch(tmp_path / "a.vtt", vtt))

    assert sample is not None
    assert sample.text == "Bonjour tout le monde"


def test_ass_takes_the_dialogue_text_field(tmp_path: Path) -> None:
    ass = (
        "[Script Info]\nTitle: English release\n\n[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,{\\i1}Hola,\\Namigo{\\i0}\n"
    )

    sample = excerpt(touch(tmp_path / "a.ass", ass))

    assert sample is not None
    assert sample.text == "Hola, amigo"


def test_a_byte_order_mark_is_honoured(tmp_path: Path) -> None:
    path = touch(tmp_path / "a.srt", SRT.encode("utf-16"))

    sample = excerpt(path)

    assert sample is not None
    assert sample.text.startswith("Привет")


def test_a_legacy_encoding_decodes_with_the_configured_charset(tmp_path: Path) -> None:
    path = touch(tmp_path / "a.srt", SRT.encode("cp1251"))

    sample = excerpt(path, charset="windows-1251")

    assert sample is not None
    assert sample.text.startswith("Привет")
    assert sample.reliable


def test_an_unknown_encoding_is_flagged_rather_than_dropped(tmp_path: Path) -> None:
    path = touch(tmp_path / "a.srt", SRT.encode("cp1251"))

    sample = excerpt(path, charset="no-such-charset")

    assert sample is not None
    assert not sample.reliable


def test_the_sample_comes_from_the_middle_and_is_capped(tmp_path: Path) -> None:
    cues = [f"{n}\n00:00:{n:02},000 --> 00:00:{n:02},500\nline {n} " + "x" * 40 for n in range(60)]
    cues[0] = "0\n00:00:00,000 --> 00:00:00,500\nSubtitles by SomeGroup"

    sample = excerpt(touch(tmp_path / "a.srt", "\n\n".join(cues)))

    assert sample is not None
    assert "SomeGroup" not in sample.text
    assert sample.text.startswith("line 20 ")
    assert len(sample.text) <= MAX_EXCERPT_CHARS


def test_a_multibyte_character_cut_by_the_read_limit_is_not_an_error(tmp_path: Path) -> None:
    header = b"1\n00:00:01,000 --> 00:00:02,000\n"
    # The two-byte "П" straddles the read limit.
    body = header + b"a" * (MAX_READ_BYTES - 1 - len(header)) + "Привет\n".encode()

    sample = excerpt(touch(tmp_path / "a.srt", body))

    assert sample is not None
    assert sample.reliable


def test_image_and_audio_formats_have_no_excerpt(tmp_path: Path) -> None:
    assert excerpt(touch(tmp_path / "a.sup", b"PG")) is None
    assert excerpt(touch(tmp_path / "a.mka", b"x")) is None


def test_a_file_with_no_dialogue_has_no_excerpt(tmp_path: Path) -> None:
    assert excerpt(touch(tmp_path / "a.srt", "signs")) is None
