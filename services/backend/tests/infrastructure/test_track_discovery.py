from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from src.core.logging import capture_log
from src.domain.errors import ProbeError
from src.domain.media import MediaInfo, Track
from src.domain.naming import EpisodeRef, parse_episode_marker, same_release
from src.infrastructure.filesystem.track_discovery import discover, release_folder
from tests.conftest import touch
from tests.stubs import StubProber


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


class TestSharedDownloadFolder:
    """A single-file torrent has no folder of its own; it sits beside other downloads."""

    @pytest.fixture
    def downloads(self, tmp_path: Path) -> Path:
        root = tmp_path / "downloads"
        other = root / "Other.Movie.2023.1080p-GRP"
        touch(other / "Other.Movie.2023.1080p-GRP.mkv")
        touch(other / "Other.Movie.2023.1080p-GRP.eng.srt", "1\n")
        touch(other / "Subs" / "2_English.srt", "1\n")
        touch(other / "RUS Sound" / "Other.Movie.2023.1080p-GRP.mka")
        return root

    def test_other_downloads_are_not_its_sidecars(self, downloads: Path) -> None:
        video = touch(downloads / "Some.Movie.2024.1080p.WEB-DL.mkv")

        assert discover(video) == []

    def test_not_even_files_named_after_it(self, downloads: Path) -> None:
        video = touch(downloads / "Some.Movie.2024.1080p.WEB-DL.mkv")
        touch(downloads / "Some.Movie.2024.1080p.WEB-DL.rus.srt", "1\n")

        assert discover(video) == []

    def test_another_shows_episode_marker_is_not_enough(self, tmp_path: Path) -> None:
        downloads = tmp_path / "downloads"
        video = touch(downloads / "Show.S01E05.1080p.WEB-DL.mkv")
        touch(downloads / "Other.Show.S01E05.1080p" / "Other.Show.S01E05.1080p.mkv")
        touch(downloads / "Other.Show.S01E05.1080p" / "Other.Show.S01E05.1080p.eng.srt", "1\n")

        assert discover(video, episode=EpisodeRef(season=1, episodes=(5,))) == []

    def test_a_loose_neighbour_gives_it_away_too(self, tmp_path: Path) -> None:
        downloads = tmp_path / "downloads"
        video = touch(downloads / "Some.Movie.2024.mkv")
        touch(downloads / "Other.Movie.2023.mkv")
        touch(downloads / "Other.Movie.2023.eng.srt", "1\n")
        touch(downloads / "Artist - Album (2020) [FLAC]" / "01 - Track.flac")

        assert discover(video) == []

    def test_the_story_says_why(self, downloads: Path) -> None:
        video = touch(downloads / "Some.Movie.2024.1080p.WEB-DL.mkv")

        with capture_log(100) as entries:
            discover(video)

        [entry] = [e for e in entries if e.stage == "discovery"]
        assert "shares its folder with other downloads" in entry.message
        assert entry.context["other_download"] == (
            "Other.Movie.2023.1080p-GRP/Other.Movie.2023.1080p-GRP.mkv"
        )

    def test_a_sample_does_not_make_a_release_folder_shared(self, download_dir: Path) -> None:
        video = touch(download_dir / "Some.Movie.2024.mkv")
        touch(download_dir / "grp-some.movie.2024-sample.mkv")
        touch(download_dir / "Subs" / "2_English.srt")

        assert [t.path.name for t in discover(video)] == ["2_English.srt"]

    def test_extras_named_after_the_show_do_not_either(self, tmp_path: Path) -> None:
        pack = tmp_path / "[Group] Show [BD 1080p]"
        video = touch(pack / "[Group] Show - 01 [BD 1080p].mkv")
        touch(pack / "[Group] Show - 02 [BD 1080p].mkv")
        touch(pack / "[Group] Show - OVA [BD 1080p].mkv")
        touch(pack / "NC" / "[Group] Show - NCOP1 [BD 1080p].mkv")

        folder = release_folder(video)

        assert folder is not None
        assert folder.stranger is None
        assert len(folder.videos) == 3


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("Show.S01E01.1080p.WEB-DL-GRP", "Show.S01E02.1080p.WEB-DL-GRP"),
        ("[Group] Show - 01 [1080p]", "[Group] Show - OVA [1080p]"),
        ("Some.Movie.2024.CD1", "Some.Movie.2024.CD2"),
        ("Some.Movie.2024.1080p", "some.movie.2024.sample"),
    ],
)
def test_same_release(a: str, b: str) -> None:
    assert same_release(a, b)


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("Some.Movie.2024.1080p", "Other.Movie.2023.1080p"),
        ("The.Bear.S03E01", "The.Boys.S04E01"),
        ("[SubsPlease] Show A - 05 (1080p)", "[SubsPlease] Show B - 03 (1080p)"),
        ("1917.2019.1080p", "300.2006.1080p"),
        ("Show.S01E05.1080p", "Some.Movie.2024.1080p"),
    ],
)
def test_different_releases(a: str, b: str) -> None:
    assert not same_release(a, b)


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


def declaring(path: Path, kind: str, language: str, **flags: bool) -> StubProber:
    track = Track(index=1, kind=kind, codec_id="A_AC3", language=language, **flags)  # type: ignore[arg-type]
    return StubProber(infos={path: MediaInfo(path=path, container="Matroska", tracks=(track,))})


class TestEmbeddedTags:
    def test_an_untagged_name_takes_the_files_own_language(self, download_dir: Path) -> None:
        video = touch(download_dir / "Some.Movie.2024.mkv")
        audio = touch(download_dir / "Some.Movie.2024.mka")

        [track] = discover(video, prober=declaring(audio, "audio", "rus", forced=True))

        assert (track.language, track.name, track.source) == ("rus", "Russian (Forced)", "tags")
        assert track.forced is True

    def test_a_language_in_the_name_beats_the_tag(self, download_dir: Path) -> None:
        video = touch(download_dir / "Some.Movie.2024.mkv")
        audio = touch(download_dir / "Some.Movie.2024.eng.mka")
        prober = declaring(audio, "audio", "rus")

        [track] = discover(video, prober=prober)

        assert (track.language, track.source) == ("eng", "heuristic")
        assert prober.probed == []

    def test_an_und_tag_changes_nothing(self, download_dir: Path) -> None:
        video = touch(download_dir / "Some.Movie.2024.mkv")
        audio = touch(download_dir / "track.mka")

        [track] = discover(video, prober=declaring(audio, "audio", "und"))

        assert (track.language, track.source) == ("und", "heuristic")

    def test_an_unreadable_file_stays_und(self, download_dir: Path) -> None:
        video = touch(download_dir / "Some.Movie.2024.mkv")
        touch(download_dir / "track.mka")

        [track] = discover(video, prober=StubProber(ProbeError("broken")))

        assert track.language == "und"

    def test_formats_without_tags_are_never_probed(self, download_dir: Path) -> None:
        video = touch(download_dir / "Some.Movie.2024.mkv")
        touch(download_dir / "Some.Movie.2024.srt", "1\n")
        touch(download_dir / "Some.Movie.2024.ac3")
        prober = StubProber()

        discover(video, prober=prober)

        assert prober.probed == []
