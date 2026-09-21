from __future__ import annotations

import shutil
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from src.db import Base
from src.db.session import DBManager
from src.infrastructure.history.repository import SqlAlchemyHistoryRepository


@pytest.fixture
async def db() -> AsyncIterator[DBManager]:
    """A private in-memory database with the schema applied.

    SQLAlchemy gives ``:memory:`` a StaticPool, so every session in one test
    sees the same database.
    """
    manager = DBManager("sqlite+aiosqlite:///:memory:")
    async with manager.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield manager
    await manager.dispose()


@pytest.fixture
async def history(db: DBManager) -> SqlAlchemyHistoryRepository:
    return SqlAlchemyHistoryRepository(db)


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
