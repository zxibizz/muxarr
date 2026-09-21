from __future__ import annotations

import json
from pathlib import Path

import pytest

from muxarr import probe as probe_module
from muxarr.errors import ProbeError
from muxarr.models import MediaInfo
from muxarr.probe import (
    MODERN_FLAG_SYNTAX_MIN_VERSION,
    parse_ffprobe_json,
    parse_mkvmerge_json,
    supports_modern_flag_syntax,
)

MKVMERGE_SAMPLE = json.dumps(
    {
        "container": {"type": "Matroska", "supported": True},
        "tracks": [
            {
                "id": 0,
                "type": "video",
                "codec": "AVC/H.264",
                "properties": {"codec_id": "V_MPEG4/ISO/AVC", "language": "und"},
            },
            {
                "id": 1,
                "type": "audio",
                "properties": {
                    "codec_id": "A_AC3",
                    "language": "eng",
                    "default_track": True,
                    "track_name": "Surround",
                },
            },
            {
                "id": 2,
                "type": "subtitles",
                "properties": {
                    "codec_id": "S_TEXT/UTF8",
                    "language": "eng",
                    "forced_track": True,
                    "flag_hearing_impaired": True,
                },
            },
            {"id": 3, "type": "buttons", "properties": {}},
        ],
    }
)

FFPROBE_SAMPLE = json.dumps(
    {
        "format": {"format_name": "matroska,webm"},
        "streams": [
            {"index": 0, "codec_type": "video", "codec_name": "h264"},
            {
                "index": 1,
                "codec_type": "audio",
                "codec_name": "ac3",
                "tags": {"language": "eng", "title": "Surround"},
                "disposition": {"default": 1},
            },
            {
                "index": 2,
                "codec_type": "subtitle",
                "codec_name": "subrip",
                "tags": {"language": "rus"},
                "disposition": {"forced": 1},
            },
            {"index": 3, "codec_type": "attachment", "codec_name": "ttf"},
        ],
    }
)


def test_parse_mkvmerge_json() -> None:
    info = parse_mkvmerge_json(Path("/x.mkv"), MKVMERGE_SAMPLE)

    assert info.container == "Matroska"
    # The "buttons" track is not something muxarr models.
    assert len(info.tracks) == 3
    assert info.audio[0].language == "eng"
    assert info.audio[0].codec_family == "ac3"
    assert info.audio[0].default is True
    assert info.subtitles[0].forced is True
    assert info.subtitles[0].hearing_impaired is True
    assert info.subtitles[0].codec_family == "srt"


def test_parse_mkvmerge_json_rejects_unsupported_container() -> None:
    payload = json.dumps({"container": {"type": "x", "supported": False}, "tracks": []})
    with pytest.raises(ProbeError, match="does not support"):
        parse_mkvmerge_json(Path("/x.bin"), payload)


def test_parse_ffprobe_json() -> None:
    info = parse_ffprobe_json(Path("/x.mkv"), FFPROBE_SAMPLE)

    assert len(info.tracks) == 3
    assert info.audio[0].codec_family == "ac3"
    assert info.subtitles[0].language == "rus"
    assert info.subtitles[0].forced is True


def test_missing_language_defaults_to_und() -> None:
    payload = json.dumps(
        {
            "container": {"type": "Matroska"},
            "tracks": [{"id": 0, "type": "audio", "properties": {}}],
        }
    )
    assert parse_mkvmerge_json(Path("/x.mkv"), payload).audio[0].language == "und"


def test_invalid_json_raises_probe_error() -> None:
    with pytest.raises(ProbeError, match="not valid JSON"):
        parse_mkvmerge_json(Path("/x.mkv"), "not json")


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        (None, False),
        ((57, 0), False),
        ((MODERN_FLAG_SYNTAX_MIN_VERSION, 0), True),
        ((81, 0), True),
    ],
)
def test_flag_syntax_detection(version: tuple[int, int] | None, expected: bool) -> None:
    assert supports_modern_flag_syntax(version) is expected


class TestProbeErrorReporting:
    """An unparseable file must not be reported as a missing tool."""

    def test_reports_the_real_failure_when_a_backend_exists(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = tmp_path / "broken.mkv"
        target.write_bytes(b"not a container")

        monkeypatch.setattr(probe_module, "has_tool", lambda name: name == "mkvmerge")

        def fail(_path: Path) -> MediaInfo:
            raise ProbeError("cannot be parsed")

        monkeypatch.setattr(probe_module, "probe_with_mkvmerge", fail)

        with pytest.raises(ProbeError, match="mkvmerge: cannot be parsed"):
            probe_module.probe(target)

    def test_reports_a_missing_backend_only_when_nothing_is_installed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = tmp_path / "video.mkv"
        target.write_bytes(b"x")

        monkeypatch.setattr(probe_module, "has_tool", lambda _name: False)

        with pytest.raises(ProbeError, match="no probe backend available"):
            probe_module.probe(target)

    def test_falls_back_to_ffprobe_when_mkvmerge_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = tmp_path / "odd.ts"
        target.write_bytes(b"x")
        expected = MediaInfo(path=target, container="mpegts", tracks=())

        monkeypatch.setattr(probe_module, "has_tool", lambda _name: True)

        def fail(_path: Path) -> MediaInfo:
            raise ProbeError("unsupported")

        monkeypatch.setattr(probe_module, "probe_with_mkvmerge", fail)
        monkeypatch.setattr(probe_module, "probe_with_ffprobe", lambda _path: expected)

        assert probe_module.probe(target) is expected
