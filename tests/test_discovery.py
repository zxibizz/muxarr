from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from muxerr.discovery import EpisodeRef, discover, parse_episode_marker
from tests.conftest import touch


def snapshot(root: Path) -> dict[str, tuple[str, int]]:
    """Checksum + mtime of every file under ``root``, for read-only assertions."""
    out: dict[str, tuple[str, int]] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            out[str(path.relative_to(root))] = (digest, path.stat().st_mtime_ns)
    return out


def test_finds_sidecars_beside_the_video(download_dir: Path) -> None:
    video = touch(download_dir / "Some.Movie.2024.mkv")
    touch(download_dir / "Some.Movie.2024.eng.srt", "1\n")
    touch(download_dir / "Some.Movie.2024.rus.ac3")

    found = {t.path.name: t for t in discover(video)}

    assert set(found) == {"Some.Movie.2024.eng.srt", "Some.Movie.2024.rus.ac3"}
    assert found["Some.Movie.2024.eng.srt"].kind == "subtitles"
    assert found["Some.Movie.2024.rus.ac3"].kind == "audio"


def test_descends_into_subs_folders(download_dir: Path) -> None:
    video = touch(download_dir / "Some.Movie.2024.mkv")
    touch(download_dir / "Subs" / "2_English.srt")
    touch(download_dir / "Subs" / "English" / "3_English.forced.srt")

    names = {t.path.name for t in discover(video)}

    assert names == {"2_English.srt", "3_English.forced.srt"}


def test_ignores_unrelated_directories(download_dir: Path) -> None:
    video = touch(download_dir / "Some.Movie.2024.mkv")
    touch(download_dir / "Sample" / "sample.eng.srt")

    assert discover(video) == []


def test_skips_other_video_files(download_dir: Path) -> None:
    video = touch(download_dir / "Some.Movie.2024.mkv")
    touch(download_dir / "Other.Movie.2024.mkv")

    assert discover(video) == []


def test_vobsub_pair_uses_idx_and_hides_bare_sub(download_dir: Path) -> None:
    video = touch(download_dir / "Some.Movie.2024.mkv")
    touch(download_dir / "Some.Movie.2024.eng.idx")
    touch(download_dir / "Some.Movie.2024.eng.sub")

    found = discover(video)

    assert [t.path.suffix for t in found] == [".idx"]
    assert found[0].companion is not None
    assert found[0].companion.suffix == ".sub"


def test_orphan_idx_is_skipped(download_dir: Path) -> None:
    video = touch(download_dir / "Some.Movie.2024.mkv")
    touch(download_dir / "Some.Movie.2024.eng.idx")

    assert discover(video) == []


def test_hidden_files_are_ignored(download_dir: Path) -> None:
    video = touch(download_dir / "Some.Movie.2024.mkv")
    touch(download_dir / "._Some.Movie.2024.eng.srt")

    assert discover(video) == []


class TestSeasonPacks:
    def test_matches_episode_marker(self, tmp_path: Path) -> None:
        pack = tmp_path / "Show.S01.1080p"
        video = touch(pack / "Show.S01E02.1080p.mkv")
        touch(pack / "Show.S01E01.1080p.mkv")
        touch(pack / "Show.S01E02.eng.srt")
        touch(pack / "Show.S01E01.eng.srt")

        found = discover(video, episode=EpisodeRef(season=1, episodes=(2,)))

        assert [t.path.name for t in found] == ["Show.S01E02.eng.srt"]

    def test_unmarked_sidecar_dropped_when_multiple_videos(self, tmp_path: Path) -> None:
        pack = tmp_path / "Show.S01.1080p"
        video = touch(pack / "Show.S01E02.1080p.mkv")
        touch(pack / "Show.S01E01.1080p.mkv")
        touch(pack / "English.srt")

        assert discover(video, episode=EpisodeRef(season=1, episodes=(2,))) == []

    def test_unmarked_sidecar_kept_for_single_episode_download(self, tmp_path: Path) -> None:
        folder = tmp_path / "Show.S01E02.1080p"
        video = touch(folder / "Show.S01E02.1080p.mkv")
        touch(folder / "English.srt")

        found = discover(video, episode=EpisodeRef(season=1, episodes=(2,)))

        assert [t.path.name for t in found] == ["English.srt"]

    def test_wrong_season_is_rejected(self, tmp_path: Path) -> None:
        pack = tmp_path / "Show"
        video = touch(pack / "Show.S02E02.mkv")
        touch(pack / "Show.S01E02.mkv")
        touch(pack / "Show.S01E02.eng.srt")

        assert discover(video, episode=EpisodeRef(season=2, episodes=(2,))) == []


@pytest.mark.parametrize(
    ("name", "season", "episodes"),
    [
        ("Show.S01E02.mkv", 1, (2,)),
        ("Show.S01E02E03.mkv", 1, (2, 3)),
        ("Show.S01E02-E03.mkv", 1, (2, 3)),
        ("Show.1x02.mkv", 1, (2,)),
        ("Show.s01.e02.mkv", 1, (2,)),
    ],
)
def test_parse_episode_marker(name: str, season: int, episodes: tuple[int, ...]) -> None:
    marker = parse_episode_marker(name)
    assert marker is not None
    assert (marker.season, marker.episodes) == (season, episodes)


def test_parse_episode_marker_returns_none_for_movies() -> None:
    assert parse_episode_marker("Some.Movie.2024.1080p.mkv") is None


def test_discovery_does_not_modify_the_source_folder(download_dir: Path) -> None:
    """The read-only invariant, at the discovery layer."""
    video = touch(download_dir / "Some.Movie.2024.mkv")
    touch(download_dir / "Some.Movie.2024.eng.srt", "1\n")
    touch(download_dir / "Subs" / "2_English.srt", "2\n")

    before = snapshot(download_dir)
    discover(video)
    after = snapshot(download_dir)

    assert before == after
