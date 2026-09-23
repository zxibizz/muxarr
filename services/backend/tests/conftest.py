from __future__ import annotations

import os
import shutil
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from src.db import Base
from src.db.session import DBManager
from src.infrastructure.history.repository import SqlAlchemyHistoryRepository

# Opt-in: point at a disposable database; every test drops and recreates its tables.
POSTGRES_URL = os.environ.get("MUXARR_TEST_POSTGRES_URL", "").strip()
DB_BACKENDS = ["sqlite", "postgres"] if POSTGRES_URL else ["sqlite"]


@pytest.fixture(params=DB_BACKENDS)
async def db(request: pytest.FixtureRequest) -> AsyncIterator[DBManager]:
    """A private database with the schema applied.

    SQLAlchemy gives ``:memory:`` a StaticPool, so every session in one test
    sees the same database.
    """
    url = POSTGRES_URL if request.param == "postgres" else "sqlite+aiosqlite:///:memory:"
    manager = DBManager(url)
    async with manager.engine.begin() as conn:
        # A test that died mid-way leaves its tables behind on Postgres.
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield manager
    async with manager.engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
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
