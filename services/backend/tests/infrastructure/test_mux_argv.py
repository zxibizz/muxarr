from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from src.application.interfaces.muxer import MuxPlan
from src.domain.errors import MuxError, ProbeError
from src.domain.media import ExternalTrack, MediaInfo, Track
from src.infrastructure.mkvtoolnix import muxer as muxer_module
from src.infrastructure.mkvtoolnix.muxer import build_argv, resolve_selectors, run_mux, verify


def plan_for(tmp_path: Path, *tracks: ExternalTrack, modern: bool = True) -> MuxPlan:
    return MuxPlan(
        source=tmp_path / "in.mkv",
        output=tmp_path / "out.mkv",
        tracks=tracks,
        modern_flags=modern,
    )


def sub(tmp_path: Path, filename: str = "eng.srt", **kwargs: object) -> ExternalTrack:
    return ExternalTrack(path=tmp_path / filename, kind="subtitles", **kwargs)  # type: ignore[arg-type]


def test_output_comes_first_and_source_precedes_sidecars(tmp_path: Path) -> None:
    argv = build_argv(plan_for(tmp_path, sub(tmp_path, language="eng")))

    assert argv[0] == "mkvmerge"
    assert argv[1:3] == ["--output", str(tmp_path / "out.mkv")]
    assert argv.index(str(tmp_path / "in.mkv")) < argv.index(str(tmp_path / "eng.srt"))


def test_per_file_options_precede_their_filename(tmp_path: Path) -> None:
    """mkvmerge applies options to the *next* file, so order is load-bearing."""
    track = sub(tmp_path, language="rus", name="Russian")
    plan = plan_for(tmp_path, track)
    argv = build_argv(plan)

    source_at = argv.index(str(plan.source))
    filename_at = argv.index(str(track.path))
    options = argv[source_at + 1 : filename_at]

    assert options[:2] == ["--language", "0:rus"]
    assert options[options.index("--track-name") + 1] == "0:Russian"


def test_added_tracks_never_claim_the_default_flag(tmp_path: Path) -> None:
    argv = build_argv(plan_for(tmp_path, sub(tmp_path, language="eng")))

    assert "--default-track-flag" in argv
    assert argv[argv.index("--default-track-flag") + 1] == "0:0"


def test_forced_and_hearing_impaired_flags(tmp_path: Path) -> None:
    track = sub(tmp_path, language="eng", forced=True, hearing_impaired=True)
    argv = build_argv(plan_for(tmp_path, track))

    assert argv[argv.index("--forced-display-flag") + 1] == "0:1"
    assert argv[argv.index("--hearing-impaired-flag") + 1] == "0:1"


def test_legacy_flag_syntax_for_old_mkvtoolnix(tmp_path: Path) -> None:
    track = sub(tmp_path, language="eng", forced=True)
    argv = build_argv(plan_for(tmp_path, track, modern=False))

    assert "--forced-track" in argv
    assert "--forced-display-flag" not in argv
    # Old mkvmerge has no hearing-impaired flag at all.
    assert "--hearing-impaired-flag" not in argv


def test_sub_charset_only_applies_to_subtitles(tmp_path: Path) -> None:
    audio = ExternalTrack(path=tmp_path / "rus.ac3", kind="audio", language="rus")
    subtitle = sub(tmp_path, language="eng")
    plan = MuxPlan(
        source=tmp_path / "in.mkv",
        output=tmp_path / "out.mkv",
        tracks=(audio, subtitle),
        sub_charset="UTF-8",
    )

    argv = build_argv(plan)
    audio_at = argv.index(str(audio.path))
    charset_at = argv.index("--sub-charset")

    assert charset_at > audio_at


def test_argv_is_a_list_of_plain_strings(tmp_path: Path) -> None:
    """Guards against a Path leaking in, which would break subprocess on some paths."""
    argv = build_argv(plan_for(tmp_path, sub(tmp_path, language="eng")))

    assert all(isinstance(item, str) for item in argv)


def test_a_resolved_selector_replaces_the_zero_prefix(tmp_path: Path) -> None:
    """An .mka whose only track is numbered 1 must be addressed as ``1:``."""
    track = ExternalTrack(path=tmp_path / "rus.mka", kind="audio", language="rus", name="Russian")
    plan = plan_for(tmp_path, track)

    argv = build_argv(plan, selectors={track.path: 1})

    assert argv[argv.index("--language") + 1] == "1:rus"
    assert argv[argv.index("--track-name") + 1] == "1:Russian"
    assert argv[argv.index("--default-track-flag") + 1] == "1:0"
    assert argv[argv.index("--forced-display-flag") + 1] == "1:0"
    assert argv[argv.index("--hearing-impaired-flag") + 1] == "1:0"


def test_selectors_default_to_zero_for_files_not_listed(tmp_path: Path) -> None:
    track = sub(tmp_path, language="eng")
    argv = build_argv(plan_for(tmp_path, track), selectors={tmp_path / "other.mka": 3})

    assert argv[argv.index("--language") + 1] == "0:eng"


def stub_probe(monkeypatch: pytest.MonkeyPatch, info: MediaInfo | Exception) -> None:
    def fake(path: Path) -> MediaInfo:
        if isinstance(info, Exception):
            raise info
        return info

    monkeypatch.setattr(muxer_module, "probe_with_mkvmerge", fake)


def test_resolve_selectors_reads_the_real_track_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """mkvmerge keeps a Matroska file's own numbering, so an .mka can start at 1."""
    track = ExternalTrack(path=tmp_path / "rus.mka", kind="audio", language="rus")
    stub_probe(
        monkeypatch,
        MediaInfo(
            path=track.path,
            container="Matroska",
            tracks=(Track(index=1, kind="audio", codec_id="A_AAC"),),
        ),
    )

    assert resolve_selectors(plan_for(tmp_path, track)) == {track.path: 1}


def test_resolve_selectors_skips_non_matroska_sidecars(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An .srt is a bare elementary stream; probing it would only cost a subprocess."""
    stub_probe(monkeypatch, ProbeError("should not be called"))

    assert resolve_selectors(plan_for(tmp_path, sub(tmp_path, language="eng"))) == {}


def test_resolve_selectors_falls_back_to_zero_when_the_probe_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    track = ExternalTrack(path=tmp_path / "rus.mka", kind="audio", language="rus")
    stub_probe(monkeypatch, ProbeError("unreadable"))

    assert resolve_selectors(plan_for(tmp_path, track)) == {}


def test_resolve_selectors_falls_back_to_zero_when_the_sidecar_holds_no_track(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    track = ExternalTrack(path=tmp_path / "rus.mka", kind="audio", language="rus")
    stub_probe(monkeypatch, MediaInfo(path=track.path, container="Matroska", tracks=()))

    assert resolve_selectors(plan_for(tmp_path, track)) == {}


def test_resolve_selectors_prefers_a_track_of_the_expected_kind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    track = ExternalTrack(path=tmp_path / "rus.mka", kind="audio", language="rus")
    stub_probe(
        monkeypatch,
        MediaInfo(
            path=track.path,
            container="Matroska",
            tracks=(
                Track(index=1, kind="subtitles", codec_id="S_TEXT/ASS"),
                Track(index=2, kind="audio", codec_id="A_AAC"),
            ),
        ),
    )

    assert resolve_selectors(plan_for(tmp_path, track)) == {track.path: 2}


class TestSourcePruning:
    def plan(self, tmp_path: Path, *tracks: ExternalTrack, **keep: object) -> MuxPlan:
        return replace(plan_for(tmp_path, *tracks), **keep)  # type: ignore[arg-type]

    def source_options(self, plan: MuxPlan) -> list[str]:
        argv = build_argv(plan)
        return argv[3 : argv.index(str(plan.source))]

    def test_nothing_is_added_when_every_track_is_kept(self, tmp_path: Path) -> None:
        assert self.source_options(self.plan(tmp_path, sub(tmp_path, language="eng"))) == []

    def test_kept_ids_precede_the_source_only(self, tmp_path: Path) -> None:
        track = sub(tmp_path, language="eng")
        plan = self.plan(tmp_path, track, keep_audio=(1, 3), keep_subtitles=(5,))

        assert self.source_options(plan) == [
            "--audio-tracks",
            "1,3",
            "--subtitle-tracks",
            "5",
        ]
        argv = build_argv(plan)
        assert "--audio-tracks" not in argv[argv.index(str(plan.source)) :]

    def test_an_empty_selection_drops_the_kind_entirely(self, tmp_path: Path) -> None:
        plan = self.plan(tmp_path, keep_audio=(), keep_subtitles=())

        assert self.source_options(plan) == ["--no-audio", "--no-subtitles"]

    def test_run_mux_refuses_only_when_there_is_nothing_to_do(self, tmp_path: Path) -> None:
        with pytest.raises(MuxError, match="nothing to strip"):
            run_mux(plan_for(tmp_path), SOURCE)

    def test_verify_counts_only_the_kept_source_tracks(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        stub_probe(monkeypatch, output_with("eng", "rus"))
        audio = ExternalTrack(path=tmp_path / "rus.mka", kind="audio", language="rus")

        verify(self.plan(tmp_path, audio, keep_audio=(1,)), SOURCE)

    def test_verify_rejects_a_track_that_should_have_gone(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        stub_probe(monkeypatch, output_with("eng", "fre"))

        with pytest.raises(MuxError, match="exactly 1 audio"):
            verify(self.plan(tmp_path, keep_audio=(1,)), SOURCE)


SOURCE = MediaInfo(
    path=Path("/in.mkv"),
    container="Matroska",
    tracks=(
        Track(index=0, kind="video", codec_id="V_MPEG4/ISO/AVC"),
        Track(index=1, kind="audio", codec_id="A_AC3", language="eng"),
        Track(index=2, kind="audio", codec_id="A_AC3", language="fre"),
    ),
)


def output_with(*audio: str) -> MediaInfo:
    return MediaInfo(
        path=Path("/out.mkv"),
        container="Matroska",
        tracks=(
            Track(index=0, kind="video", codec_id="V_MPEG4/ISO/AVC"),
            *(
                Track(index=i, kind="audio", codec_id="A_AC3", language=lang)
                for i, lang in enumerate(audio, start=1)
            ),
        ),
    )
