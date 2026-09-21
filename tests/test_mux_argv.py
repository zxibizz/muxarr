from __future__ import annotations

from pathlib import Path

from muxerr.models import ExternalTrack
from muxerr.mux import MuxPlan, build_argv


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
