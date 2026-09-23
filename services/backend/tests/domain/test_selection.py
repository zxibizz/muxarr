from __future__ import annotations

from pathlib import Path

from src.domain.media import ExternalTrack, MediaInfo, Track
from src.domain.selection import Rejection, SelectionPolicy, prune, select
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
    assert result.rejected[0].code == "already_present"


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


def test_image_subtitles_can_be_excluded(tmp_path: Path) -> None:
    candidate = external(tmp_path, "eng.sup", language="eng")
    policy = SelectionPolicy(skip_image_subtitles=True)

    assert select(container(), [candidate]).accepted == (candidate,)
    assert select(container(), [candidate], policy).accepted == ()


def test_undetermined_language_can_be_excluded(tmp_path: Path) -> None:
    candidate = external(tmp_path, "whatever.srt", language="und")

    policy = SelectionPolicy(skip_undetermined_language=True)
    rejection = select(container(), [candidate], policy).rejected[0]
    assert rejection.code == "undetermined_language"
    assert rejection.reason == "language could not be determined"


def test_max_external_tracks_is_enforced(tmp_path: Path) -> None:
    candidates = [
        external(tmp_path, f"{lang}.srt", language=lang) for lang in ("eng", "rus", "fre", "ger")
    ]

    result = select(container(), candidates, SelectionPolicy(max_external_tracks=2))

    assert len(result.accepted) == 2
    assert all(r.code == "track_limit" for r in result.rejected)


def test_audio_is_ordered_before_subtitles(tmp_path: Path) -> None:
    sub = external(tmp_path, "eng.srt", language="eng")
    aud = external(tmp_path, "rus.ac3", kind="audio", language="rus")

    result = select(container(), [sub, aud])

    assert [t.kind for t in result.accepted] == ["audio", "subtitles"]


class TestKeepLanguages:
    def source(self) -> MediaInfo:
        return container(
            Track(index=0, kind="video", codec_id="V_MPEG4/ISO/AVC", language="und"),
            Track(index=1, kind="audio", codec_id="A_AC3", language="eng"),
            Track(index=2, kind="audio", codec_id="A_AC3", language="fre"),
            Track(index=3, kind="audio", codec_id="A_AAC", language="und"),
            Track(index=4, kind="subtitles", codec_id="S_TEXT/UTF8", language="eng"),
            Track(index=5, kind="subtitles", codec_id="S_TEXT/UTF8", language="deu"),
        )

    def test_empty_lists_keep_everything(self) -> None:
        pruning = prune(self.source(), SelectionPolicy())

        assert not pruning
        assert pruning.kept == self.source()

    def test_only_listed_languages_survive(self) -> None:
        policy = SelectionPolicy(
            keep_audio_languages=frozenset({"eng"}),
            keep_subtitle_languages=frozenset({"eng"}),
        )

        pruning = prune(self.source(), policy)

        assert [t.index for t in pruning.kept.tracks] == [0, 1, 4]
        assert [t.index for t in pruning.removed] == [2, 3, 5]

    def test_video_is_never_pruned(self) -> None:
        policy = SelectionPolicy(keep_audio_languages=frozenset({"rus"}))

        assert prune(self.source(), policy).kept.video == self.source().video

    def test_undetermined_survives_only_when_listed(self) -> None:
        policy = SelectionPolicy(keep_audio_languages=frozenset({"eng", "und"}))

        assert [t.index for t in prune(self.source(), policy).removed] == [2]

    def test_bibliographic_and_terminological_codes_match(self) -> None:
        """mkvmerge may report ``deu`` where the keep list says ``ger``."""
        policy = SelectionPolicy(keep_subtitle_languages=frozenset({"ger"}))

        assert [t.index for t in prune(self.source(), policy).removed] == [4]

    def test_sidecars_in_other_languages_are_rejected(self, tmp_path: Path) -> None:
        keep = external(tmp_path, "rus.srt", language="rus")
        drop = external(tmp_path, "fre.srt", language="fre")
        policy = SelectionPolicy(keep_subtitle_languages=frozenset({"rus"}))

        result = select(container(), [keep, drop], policy)

        assert result.accepted == (keep,)
        assert result.rejected == (Rejection(drop, "language_not_kept"),)

    def test_the_list_for_one_kind_leaves_the_other_alone(self, tmp_path: Path) -> None:
        audio = external(tmp_path, "fre.ac3", kind="audio", language="fre")
        policy = SelectionPolicy(keep_subtitle_languages=frozenset({"rus"}))

        assert select(container(), [audio], policy).accepted == (audio,)
