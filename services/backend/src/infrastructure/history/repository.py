"""Operation history.

Every import decision is recorded, including the ones that deferred -- "why was
this release *not* muxed?" is the main question a history has to answer, and with
muxarr's fail-safe design deferring is the common outcome.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import CursorResult, delete, func, select

from src.application.interfaces.history import (
    MAX_PAGE_SIZE,
    OperationRecord,
    Page,
    Stats,
)
from src.db.session import DBManager
from src.domain.journal import LogEntry, RejectedTrack, TrackDetail
from src.domain.models import Operation


class SqlAlchemyHistoryRepository:
    def __init__(self, db: DBManager) -> None:
        self._db = db

    async def record(
        self,
        *,
        app: str,
        title: str,
        move_status: str,
        reason: str,
        source_path: str,
        destination_path: str,
        media_file: str | None = None,
        transfer_mode: str = "",
        season: int | None = None,
        episodes: Sequence[int] = (),
        added_tracks: Sequence[TrackDetail] = (),
        rejected_tracks: Sequence[RejectedTrack] = (),
        log: Sequence[LogEntry] = (),
        duration_ms: int = 0,
        source_bytes: int | None = None,
        output_bytes: int | None = None,
        dry_run: bool = False,
    ) -> int:
        """Append one operation, returning its id."""
        row = Operation(
            created_at=_now(),
            app=app,
            title=title,
            move_status=move_status,
            reason=reason,
            source_path=source_path,
            destination_path=destination_path,
            media_file=media_file,
            transfer_mode=transfer_mode,
            season=season,
            episodes=",".join(str(e) for e in episodes),
            added_tracks=json.dumps([t.to_dict() for t in added_tracks]),
            rejected_tracks=json.dumps([r.to_dict() for r in rejected_tracks]),
            log=json.dumps([e.to_dict() for e in log]),
            duration_ms=duration_ms,
            source_bytes=source_bytes,
            output_bytes=output_bytes,
            dry_run=int(dry_run),
        )
        async with self._db.session() as session:
            session.add(row)
            await session.commit()
            return int(row.id)

    async def get(self, operation_id: int) -> OperationRecord | None:
        async with self._db.session() as session:
            row = await session.get(Operation, operation_id)
            return _to_record(row) if row is not None else None

    async def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        status: str | None = None,
        app: str | None = None,
        query: str | None = None,
    ) -> Page:
        limit = max(1, min(limit, MAX_PAGE_SIZE))
        offset = max(0, offset)

        conditions = []
        if status:
            conditions.append(Operation.move_status == status)
        if app:
            conditions.append(Operation.app == app)
        if query:
            like = f"%{_escape_like(query)}%"
            conditions.append(
                Operation.title.like(like, escape="\\")
                | Operation.source_path.like(like, escape="\\")
                | Operation.reason.like(like, escape="\\")
            )

        async with self._db.session() as session:
            total = await session.scalar(
                select(func.count()).select_from(Operation).where(*conditions)
            )
            rows = await session.scalars(
                select(Operation)
                .where(*conditions)
                .order_by(Operation.id.desc())
                .limit(limit)
                .offset(offset)
            )
            items = [_to_record(row) for row in rows]

        return Page(items=items, total=int(total or 0), limit=limit, offset=offset)

    async def stats(self) -> Stats:
        cutoff = _iso(datetime.now(UTC) - timedelta(hours=24))
        muxed_filter = Operation.move_status != "DeferMove"

        async with self._db.session() as session:
            total = int(await session.scalar(select(func.count()).select_from(Operation)) or 0)
            muxed = int(
                await session.scalar(
                    select(func.count()).select_from(Operation).where(muxed_filter)
                )
                or 0
            )
            recent = int(
                await session.scalar(
                    select(func.count())
                    .select_from(Operation)
                    .where(Operation.created_at >= cutoff)
                )
                or 0
            )
            added = await session.scalars(
                select(Operation.added_tracks).where(muxed_filter)
            )
            tracks = sum(len(json.loads(value or "[]")) for value in added)

        return Stats(
            total=total,
            muxed=muxed,
            deferred=total - muxed,
            tracks_added=tracks,
            last_24h=recent,
        )

    async def prune(self, keep_last: int) -> int:
        if keep_last <= 0:
            return 0
        async with self._db.session() as session:
            # The id of the oldest row worth keeping; ids are monotonic, so
            # everything below it is older. SQLite has no DELETE ... LIMIT.
            cutoff = await session.scalar(
                select(Operation.id).order_by(Operation.id.desc()).offset(keep_last - 1).limit(1)
            )
            if cutoff is None:
                return 0
            result = cast(
                "CursorResult[Any]",
                await session.execute(delete(Operation).where(Operation.id < cutoff)),
            )
            await session.commit()
            return int(result.rowcount or 0)

    async def clear(self) -> int:
        async with self._db.session() as session:
            # execute() is typed as Result; a DML statement always yields a CursorResult.
            result = cast("CursorResult[Any]", await session.execute(delete(Operation)))
            await session.commit()
            return int(result.rowcount or 0)


def _now() -> str:
    return _iso(datetime.now(UTC))


def _escape_like(value: str) -> str:
    """Neutralise LIKE wildcards so a search for "%" matches a literal percent."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _iso(moment: datetime) -> str:
    return moment.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _to_record(row: Operation) -> OperationRecord:
    return OperationRecord(
        id=int(row.id),
        created_at=row.created_at,
        app=row.app,
        title=row.title,
        move_status=row.move_status,
        reason=row.reason,
        source_path=row.source_path,
        destination_path=row.destination_path,
        media_file=row.media_file,
        transfer_mode=row.transfer_mode,
        season=row.season,
        episodes=[int(e) for e in row.episodes.split(",") if e.strip()],
        added_tracks=[TrackDetail.from_stored(t) for t in json.loads(row.added_tracks or "[]")],
        rejected_tracks=[
            RejectedTrack.from_stored(r) for r in json.loads(row.rejected_tracks or "[]")
        ],
        log=[LogEntry.from_dict(e) for e in json.loads(row.log or "[]")],
        duration_ms=int(row.duration_ms),
        source_bytes=row.source_bytes,
        output_bytes=row.output_bytes,
        dry_run=bool(row.dry_run),
    )
