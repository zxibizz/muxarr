"""Job queue backed by the same SQLite database as the history.

SQLite has no row locking -- ``SELECT ... FOR UPDATE`` is silently a no-op in the
dialect -- so a job is claimed with a conditional UPDATE and confirmed by its
rowcount. Two workers racing for the same row means exactly one of them sees
``rowcount == 1``.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast, get_args

from sqlalchemy import CursorResult, delete, func, select, update
from sqlalchemy.exc import IntegrityError

from src.application.interfaces.jobs import JobConflictError, JobRecord
from src.application.use_cases.imports.dto import ImportOutcome, ImportRequest
from src.db.session import DBManager
from src.domain.enums import App, JobState, MoveStatus
from src.domain.models import Job

# How many pending rows to try before giving up on a claim pass. Only matters
# when several workers contend; with one worker the first candidate always wins.
_CLAIM_ATTEMPTS = 8


class SqlAlchemyJobRepository:
    def __init__(self, db: DBManager) -> None:
        self._db = db

    async def create_or_get(
        self, job_id: str, fingerprint: str, request: ImportRequest
    ) -> tuple[JobRecord, bool]:
        now = _now()
        row = Job(
            id=job_id,
            fingerprint=fingerprint,
            state="pending",
            app=request.app,
            source_path=str(request.source_path),
            destination_path=str(request.destination_path),
            transfer_mode=request.transfer_mode,
            dry_run=int(request.dry_run),
            created_at=now,
            updated_at=now,
        )
        async with self._db.session() as session:
            session.add(row)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
            else:
                return _to_record(row), True

        existing = await self.get(job_id)
        if existing is None:  # pragma: no cover - the row was pruned mid-flight
            raise JobConflictError(f"job {job_id} could not be created")
        if existing.fingerprint != fingerprint:
            raise JobConflictError(f"job {job_id} already exists for a different import")
        return existing, False

    async def get(self, job_id: str) -> JobRecord | None:
        async with self._db.session() as session:
            row = await session.get(Job, job_id)
            return _to_record(row) if row is not None else None

    async def claim_next(self) -> JobRecord | None:
        async with self._db.session() as session:
            candidates = list(
                await session.scalars(
                    select(Job.id)
                    .where(Job.state == "pending")
                    .order_by(Job.created_at, Job.id)
                    .limit(_CLAIM_ATTEMPTS)
                )
            )
            for job_id in candidates:
                result = cast(
                    "CursorResult[Any]",
                    await session.execute(
                        update(Job)
                        .where(Job.id == job_id, Job.state == "pending")
                        .values(state="running", updated_at=_now())
                    ),
                )
                if not result.rowcount:
                    continue
                await session.commit()
                # expire_on_commit is off, so the cached row would still say
                # "pending" without populate_existing.
                claimed = (
                    await session.execute(
                        select(Job)
                        .where(Job.id == job_id)
                        .execution_options(populate_existing=True)
                    )
                ).scalar_one()
                return _to_record(claimed)
            return None

    async def succeed(self, job_id: str, outcome: ImportOutcome, history_id: int | None) -> None:
        await self._finish(
            job_id,
            state="succeeded",
            outcome=json.dumps(_outcome_to_json(outcome)),
            history_id=history_id,
        )

    async def fail(self, job_id: str, error: str) -> None:
        await self._finish(job_id, state="failed", error=error)

    async def fail_running(self, error: str) -> int:
        async with self._db.session() as session:
            result = cast(
                "CursorResult[Any]",
                await session.execute(
                    update(Job)
                    .where(Job.state == "running")
                    .values(state="failed", error=error, updated_at=_now())
                ),
            )
            await session.commit()
            return int(result.rowcount or 0)

    async def prune(self, older_than_seconds: float) -> int:
        cutoff = _iso(datetime.now(UTC) - timedelta(seconds=older_than_seconds))
        async with self._db.session() as session:
            result = cast(
                "CursorResult[Any]",
                await session.execute(
                    delete(Job).where(
                        Job.state.in_(("succeeded", "failed")), Job.updated_at < cutoff
                    )
                ),
            )
            await session.commit()
            return int(result.rowcount or 0)

    async def counts_by_state(self) -> dict[JobState, int]:
        # Zero-filled from the Literal so the shape stays stable on an empty queue.
        counts: dict[JobState, int] = dict.fromkeys(get_args(JobState), 0)
        async with self._db.session() as session:
            rows = await session.execute(select(Job.state, func.count()).group_by(Job.state))
            for state, count in rows.all():
                counts[cast("JobState", state)] = int(count)
        return counts

    async def _finish(
        self,
        job_id: str,
        *,
        state: JobState,
        outcome: str | None = None,
        error: str | None = None,
        history_id: int | None = None,
    ) -> None:
        values: dict[str, object] = {"state": state, "updated_at": _now()}
        if outcome is not None:
            values["outcome"] = outcome
        if error is not None:
            values["error"] = error
        if history_id is not None:
            values["history_id"] = history_id
        async with self._db.session() as session:
            await session.execute(update(Job).where(Job.id == job_id).values(**values))
            await session.commit()


def _now() -> str:
    return _iso(datetime.now(UTC))


def _iso(moment: datetime) -> str:
    return moment.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _outcome_to_json(outcome: ImportOutcome) -> dict[str, Any]:
    return {
        "move_status": outcome.move_status,
        "reason": outcome.reason,
        "media_file": str(outcome.media_file) if outcome.media_file else None,
        "extra_files": [str(p) for p in outcome.extra_files],
        "prevent_extra_import": outcome.prevent_extra_import,
        "added_tracks": list(outcome.added_tracks),
        "rejected_tracks": [dict(r) for r in outcome.rejected_tracks],
        "duration_ms": outcome.duration_ms,
        "source_bytes": outcome.source_bytes,
        "output_bytes": outcome.output_bytes,
    }


def _outcome_from_json(payload: str) -> ImportOutcome:
    data = json.loads(payload)
    media_file = data.get("media_file")
    return ImportOutcome(
        move_status=cast("MoveStatus", data["move_status"]),
        reason=data["reason"],
        media_file=Path(media_file) if media_file else None,
        extra_files=tuple(Path(p) for p in data.get("extra_files", ())),
        prevent_extra_import=bool(data.get("prevent_extra_import", False)),
        added_tracks=tuple(data.get("added_tracks", ())),
        rejected_tracks=tuple(data.get("rejected_tracks", ())),
        duration_ms=int(data.get("duration_ms", 0)),
        source_bytes=data.get("source_bytes"),
        output_bytes=data.get("output_bytes"),
    )


def _to_record(row: Job) -> JobRecord:
    return JobRecord(
        id=row.id,
        fingerprint=row.fingerprint,
        state=cast("JobState", row.state),
        request=ImportRequest(
            app=cast("App", row.app),
            source_path=Path(row.source_path),
            destination_path=Path(row.destination_path),
            transfer_mode=row.transfer_mode,
            dry_run=bool(row.dry_run),
        ),
        outcome=_outcome_from_json(row.outcome) if row.outcome else None,
        error=row.error,
        history_id=row.history_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
