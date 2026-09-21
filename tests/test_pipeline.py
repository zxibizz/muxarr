from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest

from muxarr import pipeline, probe
from muxarr.config import Settings
from muxarr.errors import MuxError, ProbeError
from muxarr.models import MediaInfo, Track
from muxarr.pipeline import ImportRequest, handle_import
from tests.conftest import touch

VIDEO_ONLY = MediaInfo(
    path=Path("/x.mkv"),
    container="Matroska",
    tracks=(Track(index=0, kind="video", codec_id="V_MPEG4/ISO/AVC"),),
)


@pytest.fixture
def layout(tmp_path: Path) -> dict[str, Path]:
    downloads = tmp_path / "downloads"
    library = tmp_path / "library"
    release = downloads / "Some.Movie.2024.1080p-GRP"
    movie = library / "Some Movie (2024)"
    release.mkdir(parents=True)
    movie.mkdir(parents=True)
    return {
        "downloads": downloads,
        "library": library,
        "release": release,
        "movie": movie,
        "source": touch(release / "Some.Movie.2024.1080p-GRP.mkv", b"video"),
        "destination": movie / "Some Movie (2024).mkv",
    }


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(read_roots=(tmp_path / "downloads", tmp_path / "library"))


def request_for(layout: dict[str, Path], **overrides: Any) -> ImportRequest:
    base: dict[str, Any] = {
        "app": "radarr",
        "source_path": layout["source"],
        "destination_path": layout["destination"],
        "library_path": layout["movie"],
    }
    base.update(overrides)
    return ImportRequest(**base)


@pytest.fixture
def stub_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(probe, "probe", lambda _path: VIDEO_ONLY)


@pytest.fixture
def stub_mux(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """Replace the real mux with a stub that just creates the output file."""
    written: list[Path] = []

    def fake(request: Any, info: Any, tracks: Any, output: Path, *_: Any) -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"muxed")
        written.append(output)

    monkeypatch.setattr(pipeline, "_mux_into_place", fake)
    return written


class TestDeferPaths:
    def test_source_outside_read_roots(
        self, layout: dict[str, Path], settings: Settings, tmp_path: Path
    ) -> None:
        stray = touch(tmp_path / "elsewhere" / "video.mkv")
        outcome = handle_import(request_for(layout, source_path=stray), settings)

        assert outcome.move_status == "DeferMove"
        assert "path rejected" in outcome.reason

    def test_destination_outside_read_roots(
        self, layout: dict[str, Path], settings: Settings, tmp_path: Path
    ) -> None:
        outcome = handle_import(
            request_for(layout, destination_path=tmp_path / "elsewhere" / "out.mkv"), settings
        )

        assert outcome.move_status == "DeferMove"

    def test_reentrancy_guard_when_source_is_inside_the_library(
        self, layout: dict[str, Path], settings: Settings
    ) -> None:
        """RenameRequested makes *arr re-invoke the script with our own output."""
        already = touch(layout["movie"] / "Some Movie (2024).mkv", b"muxed")
        outcome = handle_import(request_for(layout, source_path=already), settings)

        assert outcome.move_status == "DeferMove"
        assert "already inside the library" in outcome.reason

    def test_missing_source(self, layout: dict[str, Path], settings: Settings) -> None:
        outcome = handle_import(
            request_for(layout, source_path=layout["release"] / "gone.mkv"), settings
        )

        assert outcome.move_status == "DeferMove"
        assert "does not exist" in outcome.reason

    def test_unprobeable_source(
        self, layout: dict[str, Path], settings: Settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def boom(_path: Path) -> MediaInfo:
            raise ProbeError("damaged file")

        monkeypatch.setattr(probe, "probe", boom)
        outcome = handle_import(request_for(layout), settings)

        assert outcome.move_status == "DeferMove"
        assert "could not probe" in outcome.reason

    def test_no_sidecars(
        self, layout: dict[str, Path], settings: Settings, stub_probe: None
    ) -> None:
        outcome = handle_import(request_for(layout), settings)

        assert outcome.move_status == "DeferMove"
        assert "no external tracks" in outcome.reason

    def test_all_candidates_rejected(
        self, layout: dict[str, Path], settings: Settings, stub_probe: None
    ) -> None:
        touch(layout["release"] / "Some.Movie.2024.1080p-GRP.eng.srt", b"")

        outcome = handle_import(request_for(layout), settings)

        assert outcome.move_status == "DeferMove"
        assert "nothing worth embedding" in outcome.reason

    def test_mux_failure_degrades_to_defer(
        self,
        layout: dict[str, Path],
        settings: Settings,
        stub_probe: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        touch(layout["release"] / "Some.Movie.2024.1080p-GRP.eng.srt", "1\n")

        def boom(*_: object) -> None:
            raise MuxError("mkvmerge exploded")

        monkeypatch.setattr(pipeline, "_mux_into_place", boom)
        outcome = handle_import(request_for(layout), settings)

        assert outcome.move_status == "DeferMove"
        assert "mux failed" in outcome.reason


class TestSuccessfulMux:
    @pytest.fixture(autouse=True)
    def _sidecar(self, layout: dict[str, Path]) -> None:
        touch(layout["release"] / "Some.Movie.2024.1080p-GRP.rus.srt", "1\n")

    def test_returns_rename_requested(
        self, layout: dict[str, Path], settings: Settings, stub_probe: None, stub_mux: list[Path]
    ) -> None:
        outcome = handle_import(request_for(layout), settings)

        assert outcome.move_status == "RenameRequested"
        assert outcome.media_file == layout["destination"]
        assert outcome.prevent_extra_import is True

    def test_output_is_always_mkv(
        self, layout: dict[str, Path], settings: Settings, stub_probe: None, stub_mux: list[Path]
    ) -> None:
        mp4_destination = layout["movie"] / "Some Movie (2024).mp4"

        outcome = handle_import(request_for(layout, destination_path=mp4_destination), settings)

        assert outcome.media_file is not None
        assert outcome.media_file.suffix == ".mkv"

    def test_output_shares_a_filesystem_with_the_destination(
        self, layout: dict[str, Path], settings: Settings, stub_probe: None, stub_mux: list[Path]
    ) -> None:
        """Otherwise *arr's follow-up Move becomes a full cross-device copy."""
        outcome = handle_import(request_for(layout), settings)

        assert outcome.media_file is not None
        assert outcome.media_file.parent.stat().st_dev == layout["destination"].parent.stat().st_dev

    def test_added_tracks_are_reported(
        self, layout: dict[str, Path], settings: Settings, stub_probe: None, stub_mux: list[Path]
    ) -> None:
        outcome = handle_import(request_for(layout), settings)

        assert outcome.added_tracks == ("subtitles:Russian",)

    def test_dry_run_writes_nothing(
        self, layout: dict[str, Path], settings: Settings, stub_probe: None, stub_mux: list[Path]
    ) -> None:
        outcome = handle_import(request_for(layout, dry_run=True), settings)

        assert outcome.move_status == "DeferMove"
        assert outcome.reason == "dry run"
        assert outcome.added_tracks == ("subtitles:Russian",)
        assert stub_mux == []


@pytest.mark.parametrize("transfer_mode", ["Move", "Copy", "HardLinkOrCopy"])
def test_download_folder_is_never_modified(
    layout: dict[str, Path],
    settings: Settings,
    stub_probe: None,
    stub_mux: list[Path],
    transfer_mode: str,
) -> None:
    """The read-only invariant, across every transfer mode *arr can request."""
    touch(layout["release"] / "Some.Movie.2024.1080p-GRP.rus.srt", "1\n")
    before = _snapshot(layout["downloads"])

    outcome = handle_import(request_for(layout, transfer_mode=transfer_mode), settings)

    assert outcome.move_status == "RenameRequested"
    assert _snapshot(layout["downloads"]) == before


def _snapshot(root: Path) -> dict[str, tuple[str, int]]:
    out: dict[str, tuple[str, int]] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            stat = path.stat()
            out[str(path.relative_to(root))] = (
                hashlib.sha256(path.read_bytes()).hexdigest(),
                stat.st_mtime_ns,
            )
    return out
