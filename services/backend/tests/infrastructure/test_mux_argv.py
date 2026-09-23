from __future__ import annotations

from pathlib import Path

import pytest

from src.application.interfaces.muxer import MuxPlan
from src.domain.errors import ProbeError
from src.domain.media import ExternalTrack, MediaInfo, Track
from src.infrastructure.mkvtoolnix import muxer as muxer_module
from src.infrastructure.mkvtoolnix.muxer import build_argv, resolve_selectors


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
