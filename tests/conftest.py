from __future__ import annotations

import shutil
from pathlib import Path

import pytest


@pytest.fixture
def download_dir(tmp_path: Path) -> Path:
    """An empty stand-in for a completed download folder."""
    directory = tmp_path / "downloads" / "Some.Movie.2024.1080p.BluRay.x264-GRP"
    directory.mkdir(parents=True)
    return directory


@pytest.fixture
def library_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "library" / "Some Movie (2024)"
    directory.mkdir(parents=True)
    return directory


def touch(path: Path, content: bytes | str = b"x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, str):
        path.write_text(content, encoding="utf-8")
    else:
        path.write_bytes(content)
    return path


requires_mkvmerge = pytest.mark.skipif(
    shutil.which("mkvmerge") is None,
    reason="mkvmerge not installed",
)

requires_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe not installed",
)
