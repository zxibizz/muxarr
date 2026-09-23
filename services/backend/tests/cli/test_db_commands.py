from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from sqlalchemy import text

from src.cli.__main__ import main
from src.db import Base
from src.db.migrations import expected_heads
from src.db.session import DBManager
from src.infrastructure.jobs.worker_state import SqlAlchemyWorkerStateRepository


@pytest.fixture
def db_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    url = f"sqlite+aiosqlite:///{tmp_path / 'muxarr.db'}"
    monkeypatch.setenv("MUXARR_DB_URL", url)
    monkeypatch.setenv("MUXARR_READ_ROOTS", str(tmp_path))
    return url


def _run(
    url: str, *, stamp: str | None = None, schema: bool = False, heartbeat: bool = False
) -> None:
    async def go() -> None:
        db = DBManager(url)
        try:
            async with db.engine.begin() as conn:
                if schema:
                    await conn.run_sync(Base.metadata.create_all)
                if stamp is not None:
                    await conn.execute(
                        text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
                    )
                    await conn.execute(
                        text("INSERT INTO alembic_version VALUES (:rev)"), {"rev": stamp}
                    )
            if heartbeat:
                await SqlAlchemyWorkerStateRepository(db).heartbeat()
        finally:
            await db.dispose()

    asyncio.run(go())


def test_the_migrations_have_a_single_head() -> None:
    assert len(expected_heads()) == 1


class TestWaitForSchema:
    def test_an_unmigrated_database_times_out(self, db_url: str) -> None:
        assert main(["wait-for-schema", "--timeout", "0", "--interval", "0"]) == 1

    def test_a_database_behind_head_times_out(self, db_url: str) -> None:
        _run(db_url, stamp="e919baae3319")

        assert main(["wait-for-schema", "--timeout", "0", "--interval", "0"]) == 1

    def test_a_database_at_head_returns_at_once(self, db_url: str) -> None:
        (head,) = expected_heads()
        _run(db_url, stamp=head)

        assert main(["wait-for-schema", "--timeout", "0"]) == 0

    def test_an_unreachable_database_times_out(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        missing = tmp_path / "no-such-dir" / "muxarr.db"
        monkeypatch.setenv("MUXARR_DB_URL", f"sqlite+aiosqlite:///{missing}")

        assert main(["wait-for-schema", "--timeout", "0"]) == 1


class TestWorkerAlive:
    def test_no_heartbeat_is_unhealthy(self, db_url: str) -> None:
        _run(db_url, schema=True)

        assert main(["worker-alive"]) == 1

    def test_a_fresh_heartbeat_is_healthy(self, db_url: str) -> None:
        _run(db_url, schema=True, heartbeat=True)

        assert main(["worker-alive"]) == 0
