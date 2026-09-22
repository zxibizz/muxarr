"""Integration tests that run the real mkvmerge.

Skipped unless mkvtoolnix/ffmpeg are on PATH. The dev image ships both, which is
where the mux path is actually exercised:

    docker compose -f compose.dev.yaml run --rm muxarr pytest -q

Fixtures are generated with ffmpeg's synthetic sources, so no real media is
needed and nothing is downloaded.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from src.application.use_cases.imports.dto import ImportOutcome, ImportRequest
from src.application.use_cases.imports.handle_import import HandleImportUseCase
from src.domain.paths import PathGuard
from src.infrastructure.filesystem.placement import FilesystemPlacement
from src.infrastructure.filesystem.track_discovery import FilesystemTrackDiscovery
from src.infrastructure.mkvtoolnix.muxer import MkvmergeMuxer
from src.infrastructure.probing import FallbackMediaProber
from src.settings.config import Settings
from tests.conftest import requires_ffmpeg, requires_mkvmerge

pytestmark = [requires_mkvmerge, requires_ffmpeg]


def handle_import(request: ImportRequest, settings: Settings) -> ImportOutcome:
    """The real use case, wired to the real adapters -- that is the point here."""
    return HandleImportUseCase(
        settings=settings,
        guard=PathGuard.from_roots(settings.read_roots),
        prober=FallbackMediaProber(),
        tracks=FilesystemTrackDiscovery(),
        muxer=MkvmergeMuxer(),
        placement=FilesystemPlacement(),
    ).execute(request)


SRT = """1
00:00:00,100 --> 00:00:00,900
Privet
"""


def _run(argv: list[str]) -> None:
    result = subprocess.run(argv, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise AssertionError(f"{argv[0]} failed: {result.stderr[-2000:]}")


def make_video(path: Path, *, container: str = "mkv") -> Path:
    """A one-second synthetic video with a single audio track."""
    path.parent.mkdir(parents=True, exist_ok=True)
    target = path.with_suffix(f".{container}")
    _run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc=duration=1:size=128x72:rate=5",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
            "-c:v", "mpeg4", "-c:a", "ac3", "-shortest",
            str(target),
        ]
    )
    return target


def make_audio(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", "sine=frequency=880:duration=1",
            "-c:a", "ac3", str(path),
        ]
    )
    return path


def tracks_of(path: Path) -> list[dict[str, object]]:
    result = subprocess.run(
        ["mkvmerge", "-J", str(path)], capture_output=True, text=True, check=False
    )
    assert result.returncode < 2, result.stderr
    return list(json.loads(result.stdout)["tracks"])


def of_type(path: Path, kind: str) -> list[dict[str, object]]:
    return [t for t in tracks_of(path) if t["type"] == kind]


@pytest.fixture
def release(tmp_path: Path) -> dict[str, Path]:
    downloads = tmp_path / "downloads" / "Movie.2024-GRP"
    library = tmp_path / "library" / "Movie (2024)"
    library.mkdir(parents=True)
    video = make_video(downloads / "Movie.2024-GRP.mkv")
    return {
        "downloads": tmp_path / "downloads",
        "library": tmp_path / "library",
        "release": downloads,
        "video": video,
        "destination": library / "Movie (2024).mkv",
    }


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(read_roots=(tmp_path / "downloads", tmp_path / "library"))


def import_request(release: dict[str, Path], **overrides: object) -> ImportRequest:
    base: dict[str, object] = {
        "app": "radarr",
        "source_path": release["video"],
        "destination_path": release["destination"],
    }
    base.update(overrides)
    return ImportRequest(**base)  # type: ignore[arg-type]


def test_fixture_generation_works(release: dict[str, Path]) -> None:
    assert len(of_type(release["video"], "video")) == 1
    assert len(of_type(release["video"], "audio")) == 1
    assert of_type(release["video"], "subtitles") == []


def test_embeds_an_external_subtitle(release: dict[str, Path], settings: Settings) -> None:
    (release["release"] / "Movie.2024-GRP.rus.srt").write_text(SRT, encoding="utf-8")

    outcome = handle_import(import_request(release), settings)

    assert outcome.move_status == "RenameRequested"
    assert outcome.media_file is not None
    subtitles = of_type(outcome.media_file, "subtitles")
    assert len(subtitles) == 1
    assert subtitles[0]["properties"]["language"] == "rus"  # type: ignore[index]


def test_embeds_an_external_audio_track(release: dict[str, Path], settings: Settings) -> None:
    make_audio(release["release"] / "Movie.2024-GRP.rus.ac3")

    outcome = handle_import(import_request(release), settings)

    assert outcome.media_file is not None
    audio = of_type(outcome.media_file, "audio")
    assert len(audio) == 2, "original plus the embedded dub"
    assert {t["properties"]["language"] for t in audio} == {"und", "rus"}  # type: ignore[index]


def test_original_video_and_audio_survive(release: dict[str, Path], settings: Settings) -> None:
    (release["release"] / "Movie.2024-GRP.rus.srt").write_text(SRT, encoding="utf-8")

    outcome = handle_import(import_request(release), settings)

    assert outcome.media_file is not None
    assert len(of_type(outcome.media_file, "video")) == 1
    assert len(of_type(outcome.media_file, "audio")) == 1


def test_forced_and_default_flags(release: dict[str, Path], settings: Settings) -> None:
    """Added tracks must be marked forced when named so, and never default."""
    (release["release"] / "Movie.2024-GRP.rus.forced.srt").write_text(SRT, encoding="utf-8")

    outcome = handle_import(import_request(release), settings)

    assert outcome.media_file is not None
    props = of_type(outcome.media_file, "subtitles")[0]["properties"]
    assert props["forced_track"] is True  # type: ignore[index]
    assert props["default_track"] is False  # type: ignore[index]


def test_track_name_is_written(release: dict[str, Path], settings: Settings) -> None:
    (release["release"] / "Movie.2024-GRP.rus.srt").write_text(SRT, encoding="utf-8")

    outcome = handle_import(import_request(release), settings)

    assert outcome.media_file is not None
    props = of_type(outcome.media_file, "subtitles")[0]["properties"]
    assert props["track_name"] == "Russian"  # type: ignore[index]


def test_mp4_source_is_remuxed_to_mkv(tmp_path: Path, settings: Settings) -> None:
    downloads = tmp_path / "downloads" / "Movie.2024-GRP"
    library = tmp_path / "library" / "Movie (2024)"
    library.mkdir(parents=True)
    video = make_video(downloads / "Movie.2024-GRP", container="mp4")
    (downloads / "Movie.2024-GRP.rus.srt").write_text(SRT, encoding="utf-8")

    outcome = handle_import(
        ImportRequest(
            app="radarr",
            source_path=video,
            # *arr derives the destination extension from the source, so it asks for .mp4.
            destination_path=library / "Movie (2024).mp4",
        ),
        settings,
    )

    assert outcome.media_file is not None
    assert outcome.media_file.suffix == ".mkv"
    assert outcome.media_file.is_file()
    assert len(of_type(outcome.media_file, "subtitles")) == 1


def test_multiple_same_language_dubs_both_survive(
    tmp_path: Path, settings: Settings
) -> None:
    """The anime multi-dub case, end to end through a real mux."""
    downloads = tmp_path / "downloads" / "Show.S01-GRP"
    library = tmp_path / "library" / "Show"
    library.mkdir(parents=True)
    video = make_video(downloads / "Show - S01E01 [1080p].mkv")
    make_audio(downloads / "RUS Sound [Dublyajnaya]" / "Show - S01E01 [1080p].mka")
    make_audio(downloads / "RUS Sound [RHS]" / "Show - S01E01 [1080p].mka")

    outcome = handle_import(
        ImportRequest(
            app="sonarr",
            source_path=video,
            destination_path=library / "Show - S01E01.mkv",
        ),
        settings,
    )

    assert outcome.media_file is not None
    audio = of_type(outcome.media_file, "audio")
    assert len(audio) == 3, "original plus both dubs"
    names = {t["properties"].get("track_name") for t in audio}  # type: ignore[union-attr]
    assert "Russian (Dublyajnaya)" in names
    assert "Russian (RHS)" in names


def test_download_folder_is_byte_identical_after_a_real_mux(
    release: dict[str, Path], settings: Settings
) -> None:
    """The read-only invariant, verified against the real mux."""
    (release["release"] / "Movie.2024-GRP.rus.srt").write_text(SRT, encoding="utf-8")
    before = _snapshot(release["downloads"])

    outcome = handle_import(import_request(release), settings)

    assert outcome.move_status == "RenameRequested"
    assert _snapshot(release["downloads"]) == before


def test_no_staging_files_are_left_behind(
    release: dict[str, Path], settings: Settings
) -> None:
    (release["release"] / "Movie.2024-GRP.rus.srt").write_text(SRT, encoding="utf-8")

    outcome = handle_import(import_request(release), settings)

    assert outcome.media_file is not None
    leftovers = list(outcome.media_file.parent.glob(".muxarr-*"))
    assert leftovers == []


def test_reimport_of_the_result_is_a_noop(
    release: dict[str, Path], settings: Settings
) -> None:
    """Second pass: the embedded track must not be added again."""
    (release["release"] / "Movie.2024-GRP.rus.srt").write_text(SRT, encoding="utf-8")
    first = handle_import(import_request(release), settings)
    assert first.media_file is not None

    # Simulate *arr re-invoking the script with our own output as the source.
    second = handle_import(
        import_request(release, source_path=first.media_file), settings
    )

    assert second.move_status == "DeferMove"
    assert "no external tracks" in second.reason


def _snapshot(root: Path) -> dict[str, tuple[str, int]]:
    out: dict[str, tuple[str, int]] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            out[str(path.relative_to(root))] = (
                hashlib.sha256(path.read_bytes()).hexdigest(),
                path.stat().st_mtime_ns,
            )
    return out
