from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest

from src.application.interfaces.muxer import MuxPlan
from src.application.use_cases.imports.dto import ImportRequest
from src.application.use_cases.imports.handle_import import HandleImportUseCase
from src.core.logging import capture_log
from src.domain.errors import MuxError, ProbeError
from src.domain.media import MediaInfo, Track
from src.domain.naming import EpisodeRef
from src.domain.paths import PathGuard
from src.infrastructure.filesystem.placement import FilesystemPlacement
from src.infrastructure.filesystem.track_discovery import FilesystemTrackDiscovery
from src.settings.config import Settings
from tests.conftest import touch

VIDEO_ONLY = MediaInfo(
    path=Path("/x.mkv"),
    container="Matroska",
    tracks=(Track(index=0, kind="video", codec_id="V_MPEG4/ISO/AVC"),),
)


class StubProber:
    def __init__(self, error: Exception | None = None) -> None:
        self._error = error

    def probe(self, path: Path) -> MediaInfo:
        if self._error is not None:
            raise self._error
        return VIDEO_ONLY


class StubMuxer:
    """Writes the staged output instead of shelling out to mkvmerge."""

    def __init__(self, error: Exception | None = None) -> None:
        self.written: list[Path] = []
        self._error = error

    def supports_modern_flags(self) -> bool:
        return True

    def run(self, plan: MuxPlan, source_info: MediaInfo, *, timeout: float) -> MediaInfo:
        if self._error is not None:
            raise self._error
        plan.output.parent.mkdir(parents=True, exist_ok=True)
        plan.output.write_bytes(b"muxed")
        self.written.append(plan.output)
        return source_info


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


@pytest.fixture
def muxer() -> StubMuxer:
    return StubMuxer()


def use_case(
    settings: Settings,
    *,
    prober: StubProber | None = None,
    muxer: StubMuxer | None = None,
) -> HandleImportUseCase:
    return HandleImportUseCase(
        settings=settings,
        guard=PathGuard.from_roots(settings.read_roots),
        prober=prober or StubProber(),
        tracks=FilesystemTrackDiscovery(),
        muxer=muxer or StubMuxer(),
        placement=FilesystemPlacement(),
    )


def request_for(layout: dict[str, Path], **overrides: Any) -> ImportRequest:
    base: dict[str, Any] = {
        "app": "radarr",
        "source_path": layout["source"],
        "destination_path": layout["destination"],
    }
    base.update(overrides)
    return ImportRequest(**base)


class TestEpisodeRef:
    """Sonarr's numbers are not sent any more; they come off the filenames."""

    def test_marker_is_read_from_the_release_name(self) -> None:
        request = ImportRequest(
            app="sonarr",
            source_path=Path("/downloads/Show.S01E02E03.1080p-GRP.mkv"),
            destination_path=Path("/library/Show/Season 01/Show - S01E02-E03.mkv"),
        )

        assert request.episode_ref == EpisodeRef(season=1, episodes=(2, 3))

    def test_destination_is_the_fallback(self) -> None:
        request = ImportRequest(
            app="sonarr",
            source_path=Path("/downloads/unparseable-release.mkv"),
            destination_path=Path("/library/Show/Season 01/Show - S01E02.mkv"),
        )

        assert request.episode_ref == EpisodeRef(season=1, episodes=(2,))

    def test_unmarked_names_give_none(self) -> None:
        request = ImportRequest(
            app="sonarr",
            source_path=Path("/downloads/Show.2024-01-15.mkv"),
            destination_path=Path("/library/Show/Show - 2024-01-15.mkv"),
        )

        assert request.episode_ref is None

    def test_radarr_never_looks_for_an_episode(self) -> None:
        request = ImportRequest(
            app="radarr",
            source_path=Path("/downloads/Movie.S01E02.mkv"),
            destination_path=Path("/library/Movie (2024)/Movie (2024).mkv"),
        )

        assert request.episode_ref is None


class TestDeferPaths:
    def test_source_outside_read_roots(
        self, layout: dict[str, Path], settings: Settings, tmp_path: Path
    ) -> None:
        stray = touch(tmp_path / "elsewhere" / "video.mkv")
        outcome = use_case(settings).execute(request_for(layout, source_path=stray))

        assert outcome.move_status == "DeferMove"
        assert "path rejected" in outcome.reason

    def test_destination_outside_read_roots(
        self, layout: dict[str, Path], settings: Settings, tmp_path: Path
    ) -> None:
        outcome = use_case(settings).execute(
            request_for(layout, destination_path=tmp_path / "elsewhere" / "out.mkv")
        )

        assert outcome.move_status == "DeferMove"

    def test_reimporting_our_own_output_finds_nothing_to_embed(
        self, layout: dict[str, Path], settings: Settings
    ) -> None:
        """RenameRequested makes *arr re-invoke the script with our own output."""
        already = touch(layout["movie"] / "Some Movie (2024).mkv", b"muxed")
        outcome = use_case(settings).execute(request_for(layout, source_path=already))

        assert outcome.move_status == "DeferMove"
        assert "no external tracks" in outcome.reason

    def test_missing_source(self, layout: dict[str, Path], settings: Settings) -> None:
        outcome = use_case(settings).execute(
            request_for(layout, source_path=layout["release"] / "gone.mkv")
        )

        assert outcome.move_status == "DeferMove"
        assert "does not exist" in outcome.reason

    def test_unprobeable_source(self, layout: dict[str, Path], settings: Settings) -> None:
        handler = use_case(settings, prober=StubProber(ProbeError("damaged file")))

        outcome = handler.execute(request_for(layout))

        assert outcome.move_status == "DeferMove"
        assert "could not probe" in outcome.reason

    def test_no_sidecars(self, layout: dict[str, Path], settings: Settings) -> None:
        outcome = use_case(settings).execute(request_for(layout))

        assert outcome.move_status == "DeferMove"
        assert "no external tracks" in outcome.reason

    def test_all_candidates_rejected(
        self, layout: dict[str, Path], settings: Settings
    ) -> None:
        touch(layout["release"] / "Some.Movie.2024.1080p-GRP.eng.srt", b"")

        outcome = use_case(settings).execute(request_for(layout))

        assert outcome.move_status == "DeferMove"
        assert "nothing worth embedding" in outcome.reason

    def test_mux_failure_degrades_to_defer(
        self, layout: dict[str, Path], settings: Settings
    ) -> None:
        touch(layout["release"] / "Some.Movie.2024.1080p-GRP.eng.srt", "1\n")
        handler = use_case(settings, muxer=StubMuxer(MuxError("mkvmerge exploded")))

        outcome = handler.execute(request_for(layout))

        assert outcome.move_status == "DeferMove"
        assert "mux failed" in outcome.reason


class TestSuccessfulMux:
    @pytest.fixture(autouse=True)
    def _sidecar(self, layout: dict[str, Path]) -> None:
        touch(layout["release"] / "Some.Movie.2024.1080p-GRP.rus.srt", "1\n")

    def test_returns_rename_requested(
        self, layout: dict[str, Path], settings: Settings, muxer: StubMuxer
    ) -> None:
        outcome = use_case(settings, muxer=muxer).execute(request_for(layout))

        assert outcome.move_status == "RenameRequested"
        assert outcome.media_file == layout["destination"]
        assert outcome.prevent_extra_import is True

    def test_output_is_always_mkv(
        self, layout: dict[str, Path], settings: Settings, muxer: StubMuxer
    ) -> None:
        mp4_destination = layout["movie"] / "Some Movie (2024).mp4"

        outcome = use_case(settings, muxer=muxer).execute(
            request_for(layout, destination_path=mp4_destination)
        )

        assert outcome.media_file is not None
        assert outcome.media_file.suffix == ".mkv"

    def test_output_shares_a_filesystem_with_the_destination(
        self, layout: dict[str, Path], settings: Settings, muxer: StubMuxer
    ) -> None:
        """Otherwise *arr's follow-up Move becomes a full cross-device copy."""
        outcome = use_case(settings, muxer=muxer).execute(request_for(layout))

        assert outcome.media_file is not None
        assert outcome.media_file.parent.stat().st_dev == layout["destination"].parent.stat().st_dev

    def test_added_tracks_are_reported(
        self, layout: dict[str, Path], settings: Settings, muxer: StubMuxer
    ) -> None:
        outcome = use_case(settings, muxer=muxer).execute(request_for(layout))

        assert [(t.kind, t.label, t.source) for t in outcome.added_tracks] == [
            ("subtitles", "Russian", "heuristic")
        ]

    def test_dry_run_writes_nothing(
        self, layout: dict[str, Path], settings: Settings, muxer: StubMuxer
    ) -> None:
        outcome = use_case(settings, muxer=muxer).execute(request_for(layout, dry_run=True))

        assert outcome.move_status == "DeferMove"
        assert outcome.reason == "dry run"
        assert [t.label for t in outcome.added_tracks] == ["Russian"]
        assert muxer.written == []


class TestTheStoryItTells:
    """The narrative the history shows is built from the same records stdout gets."""

    def test_every_stage_of_a_successful_import_is_accounted_for(
        self, layout: dict[str, Path], settings: Settings, muxer: StubMuxer
    ) -> None:
        touch(layout["release"] / "Some.Movie.2024.1080p-GRP.rus.srt", "1\n")

        with capture_log(100) as entries:
            use_case(settings, muxer=muxer).execute(request_for(layout))

        stages = [entry.stage for entry in entries if entry.stage]
        assert stages[0] == "guard"
        assert {"probe", "discovery", "selection", "mux", "outcome"} <= set(stages)

    def test_a_rejected_sidecar_says_why(
        self, layout: dict[str, Path], settings: Settings, muxer: StubMuxer
    ) -> None:
        touch(layout["release"] / "Some.Movie.2024.1080p-GRP.rus.srt", "1\n")
        touch(layout["release"] / "Some.Movie.2024.1080p-GRP.empty.srt", "")

        with capture_log(100) as entries:
            use_case(settings, muxer=muxer).execute(request_for(layout))

        selection = [e.message for e in entries if e.stage == "selection"]
        assert any("file is empty" in message for message in selection)
        assert any(
            "embedding subtitles Russian" in message and "from its filename" in message
            for message in selection
        )

    def test_a_deferral_records_the_reason_against_the_stage_that_caused_it(
        self, layout: dict[str, Path], settings: Settings
    ) -> None:
        handler = use_case(settings, prober=StubProber(ProbeError("no such tool")))

        with capture_log(100) as entries:
            handler.execute(request_for(layout))

        assert [e.message for e in entries if e.stage == "probe"] == [
            "deferring to *arr: could not probe source: no such tool"
        ]


@pytest.mark.parametrize("transfer_mode", ["Move", "Copy", "HardLinkOrCopy"])
def test_download_folder_is_never_modified(
    layout: dict[str, Path],
    settings: Settings,
    muxer: StubMuxer,
    transfer_mode: str,
) -> None:
    """The read-only invariant, across every transfer mode *arr can request."""
    touch(layout["release"] / "Some.Movie.2024.1080p-GRP.rus.srt", "1\n")
    before = _snapshot(layout["downloads"])

    outcome = use_case(settings, muxer=muxer).execute(
        request_for(layout, transfer_mode=transfer_mode)
    )

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
