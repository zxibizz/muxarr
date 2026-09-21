"""Worker liveness, so a dead worker is visible on /healthz.

Queued imports are invisible to the shim until they run: without this, a worker
that is not running looks exactly like a mux that is taking a long time.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import CursorResult, select, update

from src.db.session import DBManager
from src.domain.models import WorkerState

_ROW_ID = 1


class SqlAlchemyWorkerStateRepository:
    def __init__(self, db: DBManager) -> None:
        self._db = db

    async def heartbeat(self) -> None:
        now = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        async with self._db.session() as session:
            result = cast(
                "CursorResult[Any]",
                await session.execute(
                    update(WorkerState).where(WorkerState.id == _ROW_ID).values(last_seen=now)
                ),
            )
            if not result.rowcount:
                session.add(WorkerState(id=_ROW_ID, last_seen=now))
            await session.commit()

    async def last_seen(self) -> str | None:
        async with self._db.session() as session:
            seen = await session.scalar(
                select(WorkerState.last_seen).where(WorkerState.id == _ROW_ID)
            )
            return str(seen) if seen is not None else None
