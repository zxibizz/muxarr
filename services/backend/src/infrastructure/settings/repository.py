"""Persisted settings overrides.

Single row, mirroring ``worker_state``: the whole override set is written at
once so a save can never be observed half-applied by the worker.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import CursorResult, select, update

from src.application.interfaces.settings import SettingsSnapshot
from src.core.logging import get_logger
from src.db.session import DBManager
from src.domain.enums import LogComponent
from src.domain.models import AppSettings

log = get_logger(LogComponent.INFRA_SETTINGS)

_ROW_ID = 1


class SqlAlchemySettingsRepository:
    def __init__(self, db: DBManager) -> None:
        self._db = db

    async def load(self) -> SettingsSnapshot:
        async with self._db.session() as session:
            row = await session.get(AppSettings, _ROW_ID)
            if row is None:
                return SettingsSnapshot(revision=0)
            return SettingsSnapshot(revision=row.revision, overrides=_decode(row.payload))

    async def save(self, overrides: Mapping[str, str]) -> SettingsSnapshot:
        payload = json.dumps(dict(overrides), sort_keys=True)
        now = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")

        async with self._db.session() as session:
            result = cast(
                "CursorResult[Any]",
                await session.execute(
                    update(AppSettings)
                    .where(AppSettings.id == _ROW_ID)
                    .values(
                        payload=payload,
                        revision=AppSettings.revision + 1,
                        updated_at=now,
                    )
                ),
            )
            if not result.rowcount:
                session.add(
                    AppSettings(id=_ROW_ID, payload=payload, revision=1, updated_at=now)
                )
            await session.commit()

            revision = await session.scalar(
                select(AppSettings.revision).where(AppSettings.id == _ROW_ID)
            )

        return SettingsSnapshot(revision=int(revision or 1), overrides=_decode(payload))

    async def revision(self) -> int:
        async with self._db.session() as session:
            current = await session.scalar(
                select(AppSettings.revision).where(AppSettings.id == _ROW_ID)
            )
            return int(current or 0)


def _decode(payload: str) -> Mapping[str, str]:
    try:
        data = json.loads(payload)
    except ValueError:
        log.warning("stored settings payload is not JSON; ignoring it")
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(key): str(value) for key, value in data.items()}
