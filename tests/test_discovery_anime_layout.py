"""Regression tests for multi-dub anime release layouts.

Real-world shape (Russian anime release), which uses arbitrary folder names
rather than the conventional ``Subs/``:

    <release>/
        Show - S01E01 [1080p].mkv               <- videos at the root
        RUS Sound [TO Dublyajnaya]/
            Show - S01E01 [1080p].Dublyajnaya.mka
        RHS/
            Show - S01E01 [1080p].RHS.mka
        Nadpisi/                                 <- "signs", .ass subtitles
            Show - S01E01 [1080p].ass
"""

from __future__ import annotations

from pathlib import Path

import pytest

from muxerr.discovery import EpisodeRef, discover
from tests.conftest import touch

SHOW = "Hanaori-san Still Wants to Fight in the Next Life"


@pytest.fixture
def anime_release(tmp_path: Path) -> Path:
    release = tmp_path / f"{SHOW} [1080p]"
    for episode in range(1, 11):
        tag = f"{SHOW} - S01E{episode:02d} [1080p]"
        touch(release / f"{tag}.mkv", b"video")
        touch(release / "RUS Sound [TO Dublyajnaya]" / f"{tag}.Dublyajnaya.mka", b"audio")
        touch(release / "RHS" / f"{tag}.RHS.mka", b"audio")
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
