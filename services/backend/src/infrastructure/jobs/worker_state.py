"""Worker liveness, so a dead worker is visible on /healthz.

Queued imports are invisible to the shim until they run: without this, a worker
that is not running looks exactly like a mux that is taking a long time.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import CursorResult, select, update

from src.db.session import DBManager
from src.domain.health import HealthIssue
from src.domain.models import WorkerState

_ROW_ID = 1


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class SqlAlchemyWorkerStateRepository:
    def __init__(self, db: DBManager) -> None:
        self._db = db

    async def heartbeat(self) -> None:
        await self._upsert(last_seen=_now())

    async def last_seen(self) -> str | None:
        async with self._db.session() as session:
            seen = await session.scalar(
                select(WorkerState.last_seen).where(WorkerState.id == _ROW_ID)
            )
            return str(seen) if seen is not None else None

    async def report(self, issues: Sequence[HealthIssue]) -> None:
        await self._upsert(checks=json.dumps([issue.to_dict() for issue in issues]))

    async def issues(self) -> list[HealthIssue]:
        async with self._db.session() as session:
            stored = await session.scalar(
                select(WorkerState.checks).where(WorkerState.id == _ROW_ID)
            )
        found = (HealthIssue.from_stored(item) for item in json.loads(stored or "[]"))
        return [issue for issue in found if issue is not None]

    async def _upsert(self, **values: str) -> None:
        async with self._db.session() as session:
            result = cast(
                "CursorResult[Any]",
                await session.execute(
                    update(WorkerState).where(WorkerState.id == _ROW_ID).values(**values)
                ),
            )
            if not result.rowcount:
                session.add(WorkerState(id=_ROW_ID, **{"last_seen": _now(), **values}))
            await session.commit()
