"""Regression tests for multi-dub anime release layouts.

Real-world shape (Russian anime release), which uses arbitrary folder names
rather than the conventional ``Subs/``:

    <release>/
        Show - S01E01 [1080p].mkv               <- videos at the root
        RUS Sound [TO Dublyajnaya]/
            Show - S01E01 [1080p].Dublyajnaya.mka
        RUS Sound [RHS]/
            Show - S01E01 [1080p].RHS.mka
        Nadpisi/                                 <- "signs", .ass subtitles
            Show - S01E01 [1080p].ass
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.domain.media import MediaInfo
from src.domain.naming import EpisodeRef
from src.domain.selection import select
from src.infrastructure.filesystem.track_discovery import discover
from tests.conftest import touch

SHOW = "Hanaori-san Still Wants to Fight in the Next Life"


@pytest.fixture
def anime_release(tmp_path: Path) -> Path:
    release = tmp_path / f"{SHOW} [1080p]"
    for episode in range(1, 11):
        tag = f"{SHOW} - S01E{episode:02d} [1080p]"
        touch(release / f"{tag}.mkv", b"video")
        touch(release / "RUS Sound [TO Dublyajnaya]" / f"{tag}.Dublyajnaya.mka", b"audio")
        touch(release / "RUS Sound [RHS]" / f"{tag}.RHS.mka", b"audio")
        touch(release / "Nadpisi" / f"{tag}.ass", "signs")
    return release


def test_finds_audio_in_arbitrarily_named_folders(anime_release: Path) -> None:
    video = anime_release / f"{SHOW} - S01E08 [1080p].mkv"

    found = discover(video, episode=EpisodeRef(season=1, episodes=(8,)))

    names = sorted(t.path.name for t in found)
    assert names == [
        f"{SHOW} - S01E08 [1080p].Dublyajnaya.mka",
        f"{SHOW} - S01E08 [1080p].RHS.mka",
        f"{SHOW} - S01E08 [1080p].ass",
    ]


def test_does_not_leak_other_episodes(anime_release: Path) -> None:
    video = anime_release / f"{SHOW} - S01E08 [1080p].mkv"

    found = discover(video, episode=EpisodeRef(season=1, episodes=(8,)))

    assert all("S01E08" in t.path.name for t in found)


def test_both_dubs_are_kept_as_separate_tracks(anime_release: Path) -> None:
    video = anime_release / f"{SHOW} - S01E08 [1080p].mkv"

    found = discover(video, episode=EpisodeRef(season=1, episodes=(8,)))
    audio = [t for t in found if t.kind == "audio"]

    assert len(audio) == 2


def test_language_comes_from_the_folder_name(anime_release: Path) -> None:
    """The filename says only "Dublyajnaya"; "RUS Sound" carries the language."""
    video = anime_release / f"{SHOW} - S01E08 [1080p].mkv"

    found = discover(video, episode=EpisodeRef(season=1, episodes=(8,)))
    dub = next(t for t in found if "Dublyajnaya" in t.path.name)

    assert dub.language == "rus"


def test_variant_tags_distinguish_the_dub_groups(anime_release: Path) -> None:
    video = anime_release / f"{SHOW} - S01E08 [1080p].mkv"

    found = discover(video, episode=EpisodeRef(season=1, episodes=(8,)))
    variants = {t.variant for t in found if t.kind == "audio"}

    assert variants == {"Dublyajnaya", "RHS"}


def test_track_titles_are_human_readable(anime_release: Path) -> None:
    video = anime_release / f"{SHOW} - S01E08 [1080p].mkv"

    found = discover(video, episode=EpisodeRef(season=1, episodes=(8,)))
    titles = {t.name for t in found if t.kind == "audio"}

    assert titles == {"Russian (Dublyajnaya)", "Russian (RHS)"}


def test_selection_keeps_both_same_language_dubs(anime_release: Path) -> None:
    """Without a variant discriminator these would collapse into one track."""
    video = anime_release / f"{SHOW} - S01E08 [1080p].mkv"
    empty = MediaInfo(path=video, container="Matroska", tracks=())

    found = discover(video, episode=EpisodeRef(season=1, episodes=(8,)))
    chosen = select(empty, found)

    audio = [t for t in chosen.accepted if t.kind == "audio"]
    assert len(audio) == 2
    assert chosen.rejected == ()


def test_signs_subtitles_are_marked_forced(tmp_path: Path) -> None:
    release = tmp_path / "release"
    tag = f"{SHOW} - S01E01 [1080p]"
    touch(release / f"{tag}.mkv", b"video")
    touch(release / "Надписи" / f"{tag}.ass", "signs")

    found = discover(release / f"{tag}.mkv", episode=EpisodeRef(season=1, episodes=(1,)))

    assert len(found) == 1
    assert found[0].forced is True


def test_excluded_folders_are_not_scanned(tmp_path: Path) -> None:
    release = tmp_path / "release"
    tag = f"{SHOW} - S01E01 [1080p]"
    touch(release / f"{tag}.mkv", b"video")
    touch(release / "Extras" / f"{tag}.eng.srt", "nope")
    touch(release / "Sample" / f"{tag}.rus.mka", b"nope")

    assert discover(release / f"{tag}.mkv", episode=EpisodeRef(season=1, episodes=(1,))) == []


def test_unknown_language_falls_back_to_und_with_variant_title(tmp_path: Path) -> None:
    """Neither filename nor folder says a language, so don't invent one."""
    release = tmp_path / "release"
    tag = f"{SHOW} - S01E01 [1080p]"
    touch(release / f"{tag}.mkv", b"video")
    touch(release / "AniLibria" / f"{tag}.mka", b"audio")

    found = discover(release / f"{tag}.mkv", episode=EpisodeRef(season=1, episodes=(1,)))

    assert found[0].language == "und"
    assert found[0].variant == "AniLibria"
    assert found[0].name == "AniLibria"
