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

    def test_absolute_numbered_sidecars_named_after_the_video(self, tmp_path: Path) -> None:
        # Anime packs carry no SxxEyy; each dub folder repeats the video's own name.
        pack = tmp_path / "Mirai Nikki [480p]"
        name = "[Unknown] Mirai Nikki {:02d} [BDrip 854x480 x264 Vorbis]"
        for number in (1, 5, 10, 15):
            touch(pack / f"{name.format(number)}.mkv")
            touch(pack / "RUS Sound[metalrus]" / f"{name.format(number)}.mka")
            touch(pack / "RUS Subs" / f"{name.format(number)}.ass")
        video = pack / f"{name.format(1)}.mkv"

        found = discover(video, episode=EpisodeRef(season=1, episodes=(1,)))

        assert sorted(t.path.relative_to(pack).as_posix() for t in found) == [
            f"RUS Sound[metalrus]/{name.format(1)}.mka",
            f"RUS Subs/{name.format(1)}.ass",
        ]

    def test_a_longer_episode_number_is_not_named_after_the_video(self, tmp_path: Path) -> None:
        pack = tmp_path / "Show"
        video = touch(pack / "Show 1.mkv")
        touch(pack / "Show 10.mkv")
        touch(pack / "Show 10.mka")

        assert discover(video, episode=EpisodeRef(season=1, episodes=(1,))) == []

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
        assert "may be shared with other downloads" in entry.message
        assert entry.context["other_video"] == (
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
        assert not folder.ambiguous
        assert len(folder.videos) == 3


class TestPackWithVideosOfItsOwn:
    """Menus and bonus clips are named unlike the episodes, in folders named anything."""

    @pytest.fixture
    def pack(self, tmp_path: Path) -> Path:
        pack = tmp_path / "downloads" / "Show [BDRip] [1080p]"
        for number in ("01", "02"):
            touch(pack / f"[Group] Show {number} [BDrip 1080p].mkv")
            touch(pack / "RUS Sound [Studio]" / f"[Group] Show {number} [BDrip 1080p].mka")
            touch(pack / "RUS Sub" / f"[Group] Show {number} [BDrip 1080p].ass", "x")
        touch(pack / "Меню диска" / "Disc Menu (Vol 1).mkv")
        touch(pack / "Меню диска" / "Disc Menu (Vol 1).rus.mka")
        return pack

    def found(self, pack: Path, number: int) -> list[str]:
        video = pack / f"[Group] Show {number:02d} [BDrip 1080p].mkv"
        tracks = discover(video, episode=EpisodeRef(season=1, episodes=(number,)))
        return sorted(t.path.relative_to(pack).as_posix() for t in tracks)

    def test_sidecars_named_after_the_episode_are_its_own(self, pack: Path) -> None:
        assert self.found(pack, 1) == [
            "RUS Sound [Studio]/[Group] Show 01 [BDrip 1080p].mka",
            "RUS Sub/[Group] Show 01 [BDrip 1080p].ass",
        ]

    def test_a_loose_menu_does_not_hide_them_either(self, pack: Path) -> None:
        touch(pack / "Menu.mkv")

        assert len(self.found(pack, 2)) == 2

    def test_the_menu_folder_is_the_menus(self, pack: Path) -> None:
        folder = release_folder(pack / "[Group] Show 01 [BDrip 1080p].mkv")

        assert folder is not None
        assert folder.foreign
        assert not folder.ambiguous
        assert not any("Меню" in p.as_posix() for p, _context in folder.candidates)

    def test_a_movie_keeps_its_subs_beside_a_making_of(self, tmp_path: Path) -> None:
        pack = tmp_path / "Some.Movie.2024.1080p.BluRay"
        video = touch(pack / "Some.Movie.2024.1080p.BluRay.mkv")
        touch(pack / "Making Of" / "Behind the scenes.mkv")
        touch(pack / "Making Of" / "Behind the scenes.eng.srt", "1\n")
        touch(pack / "Subs" / "2_English.srt", "1\n")

        assert [t.path.name for t in discover(video)] == ["2_English.srt"]

    def test_episode_markers_still_pair_a_web_pack(self, tmp_path: Path) -> None:
        pack = tmp_path / "Show.S01.1080p.WEB-DL"
        video = touch(pack / "Show.S01E01.1080p.WEB-DL.mkv")
        touch(pack / "Show.S01E02.1080p.WEB-DL.mkv")
        touch(pack / "Subs" / "Show.S01E01.rus.srt", "1\n")
        touch(pack / "Subs" / "Show.S01E02.rus.srt", "1\n")
        touch(pack / "Меню диска" / "Disc Menu.mkv")

        found = discover(video, episode=EpisodeRef(season=1, episodes=(1,)))

        assert [t.path.name for t in found] == ["Show.S01E01.rus.srt"]

    def test_a_folder_named_otherwise_keeps_tracks_named_after_the_video(
        self, tmp_path: Path
    ) -> None:
        # A pack titled in another script than its files is not recognisably its
        # release's, so only the strict rule applies -- and still finds the dub.
        pack = tmp_path / "Одному лишь Богу ведомый мир [BDRip]"
        video = touch(pack / "[Group] Kami nomi 01 [BD].mkv")
        touch(pack / "[Group] Kami nomi 02 [BD].mkv")
        touch(pack / "RUS Sound" / "[Group] Kami nomi 01 [BD].mka")
        touch(pack / "BD menu (Vol 1).mkv")

        found = discover(video, episode=EpisodeRef(season=1, episodes=(1,)))

        assert [t.path.name for t in found] == ["[Group] Kami nomi 01 [BD].mka"]


class TestVideosOfItsOwnKeepTheirTracks:
    def test_a_loose_trailer_keeps_its_subtitles(self, tmp_path: Path) -> None:
        pack = tmp_path / "Some.Movie.2024.1080p"
        video = touch(pack / "Some.Movie.2024.1080p.mkv")
        touch(pack / "Trailer.mkv")
        touch(pack / "Trailer.eng.srt", "1\n")

        assert discover(video) == []

    def test_a_loose_opening_makes_unmarked_sidecars_ambiguous(self, tmp_path: Path) -> None:
        pack = tmp_path / "Show.S01E01.1080p"
        video = touch(pack / "Show.S01E01.1080p.mkv")
        touch(pack / "NCOP.mkv")
        touch(pack / "NCOP.eng.ass", "x")
        touch(pack / "Subs" / "eng.ass", "x")

        assert discover(video, episode=EpisodeRef(season=1, episodes=(1,))) == []

    def test_only_the_folder_holding_a_clip_is_skipped(self, tmp_path: Path) -> None:
        pack = tmp_path / "Show.S01.1080p"
        video = touch(pack / "Show.S01E01.1080p.mkv")
        touch(pack / "Show.S01E02.1080p.mkv")
        touch(pack / "RUS" / "Bonus clips" / "clip.mkv")
        touch(pack / "RUS" / "Bonus clips" / "clip.rus.srt", "1\n")
        touch(pack / "RUS" / "Subs" / "Show.S01E01.rus.srt", "1\n")

        found = discover(video, episode=EpisodeRef(season=1, episodes=(1,)))

        assert [t.path.name for t in found] == ["Show.S01E01.rus.srt"]

    def test_a_bonus_disc_keeps_its_subtitles(self, tmp_path: Path) -> None:
        pack = tmp_path / "Some.Movie.2024.1080p"
        video = touch(pack / "Some.Movie.2024.1080p.mkv")
        touch(pack / "Bonus Disc" / "Featurette A" / "Featurette A.mkv")
        touch(pack / "Bonus Disc" / "Subs" / "English.srt", "1\n")
        touch(pack / "Subs" / "2_English.srt", "1\n")

        assert [t.path.name for t in discover(video)] == ["2_English.srt"]

    def test_a_stray_clip_in_a_dub_folder_does_not_hide_the_dub(self, tmp_path: Path) -> None:
        pack = tmp_path / "Show [BD]"
        video = touch(pack / "[G] Show 01 [BD].mkv")
        touch(pack / "[G] Show 02 [BD].mkv")
        touch(pack / "RUS Sound" / "[G] Show 01 [BD].mka")
        touch(pack / "RUS Sound" / "[G] Show 02 [BD].mka")
        touch(pack / "RUS Sound" / "Opening RUS.mkv")

        found = discover(video, episode=EpisodeRef(season=1, episodes=(1,)))

        assert [t.path.name for t in found] == ["[G] Show 01 [BD].mka"]

    def test_tags_do_not_make_a_release_folder_unrecognisable(self, tmp_path: Path) -> None:
        pack = tmp_path / "Kimi no Na wa (2016) [BD 1080p]"
        video = touch(pack / "[Group] Kimi no Na wa [BD 1080p HEVC].mkv")
        touch(pack / "NC" / "NCED.mkv")
        touch(pack / "Subs" / "eng.srt", "1\n")

        folder = release_folder(video)

        assert folder is not None
        assert folder.own
        assert [t.path.name for t in discover(video)] == ["eng.srt"]

    def test_a_title_containing_sample_is_still_a_release(self, tmp_path: Path) -> None:
        pack = tmp_path / "Free.Samples.2012.1080p"
        video = touch(pack / "Free.Samples.2012.1080p.mkv")
        touch(pack / "Making Of" / "bts.mkv")
        touch(pack / "Subs" / "eng.srt", "1\n")

        assert [t.path.name for t in discover(video)] == ["eng.srt"]


@pytest.mark.parametrize(
    ("folder", "stem"),
    [
        ("[torrents]", "Some.Movie.2024"),
        ("movies", "Movies.That.Matter.2020"),
        ("downloads", "Show.S01E01"),
        ("Sample", "Some.Movie.2024"),
    ],
)
def test_a_download_directory_is_not_taken_for_a_release(
    tmp_path: Path, folder: str, stem: str
) -> None:
    root = tmp_path / folder
    video = touch(root / f"{stem}.mkv")
    touch(root / "Other.2023.mkv")
    touch(root / "Other.2023.eng.srt", "1\n")

    folder_of = release_folder(video)

    assert folder_of is not None
    assert folder_of.ambiguous
    assert discover(video) == []


class TestSharedDownloadFolderStillGivesNothingAway:
    def test_an_album_beside_a_single_file_download(self, tmp_path: Path) -> None:
        downloads = tmp_path / "downloads"
        video = touch(downloads / "Some.Movie.2024.mkv")
        touch(downloads / "Other.Movie.2023" / "Other.Movie.2023.mkv")
        touch(downloads / "Artist - Album (2020) [FLAC]" / "01 - Track.flac")

        assert discover(video) == []

    def test_another_release_named_like_it_keeps_its_tracks(self, tmp_path: Path) -> None:
        downloads = tmp_path / "downloads"
        video = touch(downloads / "Show.S01E01.mkv")
        touch(downloads / "Show.S01E01 [Other]" / "Other.Cut.mkv")
        touch(downloads / "Show.S01E01 [Other]" / "Show.S01E01.rus.mka")

        assert discover(video, episode=EpisodeRef(season=1, episodes=(1,))) == []

    def test_another_cut_of_the_same_title_keeps_its_tracks(self, tmp_path: Path) -> None:
        downloads = tmp_path / "downloads"
        video = touch(downloads / "Show.S01E01.1080p.mkv")
        touch(downloads / "Other.Movie.2023" / "Other.Movie.2023.mkv")
        repack = downloads / "Show.S01E01.1080p.REPACK-OTHER"
        touch(repack / "Show.S01E01.1080p.REPACK-OTHER.mkv")
        touch(repack / "Show.S01E01.1080p.REPACK-OTHER.rus.srt", "1\n")

        assert discover(video, episode=EpisodeRef(season=1, episodes=(1,))) == []

    def test_loose_files_beside_single_file_episodes(self, tmp_path: Path) -> None:
        downloads = tmp_path / "downloads"
        video = touch(downloads / "Show.S01E01.mkv")
        touch(downloads / "Show.S01E02.mkv")
        touch(downloads / "Show.S01E01.rus.srt", "1\n")
        touch(downloads / "Other.Movie" / "Other.Movie.mkv")

        assert discover(video, episode=EpisodeRef(season=1, episodes=(1,))) == []

    def test_a_dub_pack_for_exactly_this_file_is_taken(self, tmp_path: Path) -> None:
        downloads = tmp_path / "downloads"
        video = touch(downloads / "Some.Movie.2024.1080p.WEB-DL.mkv")
        touch(downloads / "Other.Movie.2023" / "Other.Movie.2023.mkv")
        touch(downloads / "Some.Movie RUS dub" / "Some.Movie.2024.1080p.WEB-DL.rus.mka")

        assert [t.path.name for t in discover(video)] == ["Some.Movie.2024.1080p.WEB-DL.rus.mka"]


@pytest.mark.parametrize(
    "menus",
    [
        "BD menu",
        "BD Menus",
        "BDMenu",
        "BD_Menu",
        "BD-Menu [1080p]",
        "Menu",
        "Menus (BD)",
        "Bonus",
        "Bonuses",
        "[Bonus]",
        "Extras [BD]",
    ],
)
def test_disc_menus_do_not_make_a_pack_look_shared(tmp_path: Path, menus: str) -> None:
    # A BDRip pack ships the disc menus as videos with names of their own
    # ("BD menu (Vol 1).mkv"); they must not hide the dubs from every episode.
    pack = tmp_path / "Show [BDRip] [1080p]"
    video = touch(pack / "[Group] Show 01 [BDrip 1080p].mkv")
    touch(pack / "[Group] Show 02 [BDrip 1080p].mkv")
    touch(pack / menus / "BD menu (Vol 1).mkv")
    touch(pack / "RUS Sound [Studio]" / "[Group] Show 01 [BDrip 1080p].mka")
    touch(pack / "RUS Sound [Studio]" / "[Group] Show 02 [BDrip 1080p].mka")

    found = discover(video, episode=EpisodeRef(season=1, episodes=(1,)))

    assert [t.path.relative_to(pack).as_posix() for t in found] == [
        "RUS Sound [Studio]/[Group] Show 01 [BDrip 1080p].mka"
    ]


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
