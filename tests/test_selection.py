from __future__ import annotations

from pathlib import Path

from muxerr.models import ExternalTrack, MediaInfo, Track
from muxerr.selection import SelectionPolicy, select
from tests.conftest import touch


def container(*tracks: Track) -> MediaInfo:
    return MediaInfo(path=Path("/x.mkv"), container="Matroska", tracks=tracks)


def audio_track(language: str, codec: str = "A_AC3") -> Track:
    return Track(index=1, kind="audio", codec_id=codec, language=language)


def subtitle_track(language: str, *, forced: bool = False, codec: str = "S_TEXT/UTF8") -> Track:
    return Track(index=2, kind="subtitles", codec_id=codec, language=language, forced=forced)


def external(
    tmp_path: Path, filename: str, kind: str = "subtitles", **kwargs: object
) -> ExternalTrack:
    path = touch(tmp_path / filename, "content")
    return ExternalTrack(path=path, kind=kind, **kwargs)  # type: ignore[arg-type]


def test_accepts_a_new_language(tmp_path: Path) -> None:
    info = container(audio_track("eng"))
    candidate = external(tmp_path, "rus.srt", language="rus")

    result = select(info, [candidate])

    assert result.accepted == (candidate,)
    assert result.rejected == ()


def test_rejects_duplicate_language_and_codec(tmp_path: Path) -> None:
    info = container(subtitle_track("eng"))
    candidate = external(tmp_path, "eng.srt", language="eng")

    result = select(info, [candidate])

    assert result.accepted == ()
    assert result.rejected[0][1] == "already present in container"


def test_forced_variant_is_not_a_duplicate(tmp_path: Path) -> None:
    """An existing English sub must not block an English *forced* sub."""
    info = container(subtitle_track("eng"))
    candidate = external(tmp_path, "eng.forced.srt", language="eng", forced=True)

    assert select(info, [candidate]).accepted == (candidate,)


def test_language_mode_ignores_codec(tmp_path: Path) -> None:
    info = container(subtitle_track("eng", codec="S_TEXT/ASS"))
    candidate = external(tmp_path, "eng.srt", language="eng")

    strict = select(info, [candidate], SelectionPolicy(dedupe="language_codec"))
    loose = select(info, [candidate], SelectionPolicy(dedupe="language"))

    assert strict.accepted == (candidate,)
    assert loose.accepted == ()


def test_dedupe_off_accepts_everything(tmp_path: Path) -> None:
    info = container(subtitle_track("eng"))
    candidate = external(tmp_path, "eng.srt", language="eng")

    assert select(info, [candidate], SelectionPolicy(dedupe="off")).accepted == (candidate,)


def test_duplicate_candidates_are_collapsed(tmp_path: Path) -> None:
    """The same track in both the root and Subs/ should only be embedded once."""
    info = container()
    first = external(tmp_path, "eng.srt", language="eng")
    second = external(tmp_path / "Subs", "2_English.srt", language="eng")

    result = select(info, [first, second])

    assert len(result.accepted) == 1
    assert len(result.rejected) == 1


def test_empty_files_are_rejected(tmp_path: Path) -> None:
    path = touch(tmp_path / "eng.srt", b"")
    candidate = ExternalTrack(path=path, kind="subtitles", language="eng")

    assert select(container(), [candidate]).rejected[0][1] == "file is empty"


def test_missing_files_are_rejected(tmp_path: Path) -> None:
    candidate = ExternalTrack(path=tmp_path / "gone.srt", kind="subtitles", language="eng")

    assert select(container(), [candidate]).rejected[0][1] == "file disappeared before muxing"


def test_image_subtitles_can_be_excluded(tmp_path: Path) -> None:
    candidate = external(tmp_path, "eng.sup", language="eng")
    policy = SelectionPolicy(skip_image_subtitles=True)

    assert select(container(), [candidate]).accepted == (candidate,)
    assert select(container(), [candidate], policy).accepted == ()


def test_undetermined_language_can_be_excluded(tmp_path: Path) -> None:
    candidate = external(tmp_path, "whatever.srt", language="und")

    policy = SelectionPolicy(skip_undetermined_language=True)
    assert select(container(), [candidate], policy).rejected[0][1] == (
        "language could not be determined"
    )


def test_max_external_tracks_is_enforced(tmp_path: Path) -> None:
    candidates = [
        external(tmp_path, f"{lang}.srt", language=lang) for lang in ("eng", "rus", "fre", "ger")
    ]

    result = select(container(), candidates, SelectionPolicy(max_external_tracks=2))

    assert len(result.accepted) == 2
    assert all(reason == "max_external_tracks reached" for _, reason in result.rejected)


def test_audio_is_ordered_before_subtitles(tmp_path: Path) -> None:
    sub = external(tmp_path, "eng.srt", language="eng")
    aud = external(tmp_path, "rus.ac3", kind="audio", language="rus")

    result = select(container(), [sub, aud])

    assert [t.kind for t in result.accepted] == ["audio", "subtitles"]
