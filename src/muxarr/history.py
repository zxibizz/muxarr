"""Operation history.

Every import decision is recorded, including the ones that deferred -- "why was
this release *not* muxed?" is the main question a history has to answer, and with
muxarr's fail-safe design deferring is the common outcome.

The log lives in an in-memory SQLite database and dies with the process. A single
connection guarded by a lock is plenty at this write volume, and it is also what
makes the store usable from more than one thread.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

MAX_PAGE_SIZE = 500

_SCHEMA = """
CREATE TABLE IF NOT EXISTS operations (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at       TEXT    NOT NULL,
    app              TEXT    NOT NULL,
    title            TEXT    NOT NULL,
    move_status      TEXT    NOT NULL,
    reason           TEXT    NOT NULL,
    source_path      TEXT    NOT NULL,
    destination_path TEXT    NOT NULL,
    media_file       TEXT,
    transfer_mode    TEXT    NOT NULL DEFAULT '',
    season           INTEGER,
    episodes         TEXT    NOT NULL DEFAULT '',
    added_tracks     TEXT    NOT NULL DEFAULT '[]',
    rejected_tracks  TEXT    NOT NULL DEFAULT '[]',
    duration_ms      INTEGER NOT NULL DEFAULT 0,
    source_bytes     INTEGER,
    output_bytes     INTEGER,
    dry_run          INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_operations_created ON operations (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_operations_status  ON operations (move_status);
CREATE INDEX IF NOT EXISTS idx_operations_app     ON operations (app);
"""


@dataclass(frozen=True, slots=True)
class Operation:
    id: int
    created_at: str
    app: str
    title: str
    move_status: str
    reason: str
    source_path: str
    destination_path: str
    media_file: str | None
    transfer_mode: str
    season: int | None
    episodes: list[int]
    added_tracks: list[str]
    rejected_tracks: list[dict[str, str]]
    duration_ms: int
    source_bytes: int | None
    output_bytes: int | None
    dry_run: bool

    @property
    def muxed(self) -> bool:
        return self.move_status != "DeferMove"


@dataclass(frozen=True, slots=True)
class Stats:
    total: int
    muxed: int
    deferred: int
    tracks_added: int
    last_24h: int


@dataclass(frozen=True, slots=True)
class Page:
    items: list[Operation]
    total: int
    limit: int
    offset: int


class HistoryStore:
    """Append-only log of import decisions."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(":memory:", check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def record(
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
        added_tracks: Sequence[str] = (),
        rejected_tracks: Sequence[dict[str, str]] = (),
        duration_ms: int = 0,
        source_bytes: int | None = None,
        output_bytes: int | None = None,
        dry_run: bool = False,
    ) -> int:
        """Append one operation, returning its id."""
        with self._lock:
            cursor = self._conn.execute(
                """
                INSERT INTO operations (
                    created_at, app, title, move_status, reason, source_path,
                    destination_path, media_file, transfer_mode,
                    season, episodes, added_tracks, rejected_tracks, duration_ms,
                    source_bytes, output_bytes, dry_run
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    _now(),
                    app,
                    title,
                    move_status,
                    reason,
                    source_path,
                    destination_path,
                    media_file,
                    transfer_mode,
                    season,
                    ",".join(str(e) for e in episodes),
                    json.dumps(list(added_tracks)),
                    json.dumps([dict(r) for r in rejected_tracks]),
                    duration_ms,
                    source_bytes,
                    output_bytes,
                    int(dry_run),
                ),
            )
            self._conn.commit()
            return int(cursor.lastrowid or 0)

    def get(self, operation_id: int) -> Operation | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM operations WHERE id = ?", (operation_id,)
            ).fetchone()
        return _to_operation(row) if row else None

    def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        status: str | None = None,
        app: str | None = None,
        query: str | None = None,
    ) -> Page:
        clauses: list[str] = []
        params: list[Any] = []

        if status:
            clauses.append("move_status = ?")
            params.append(status)
        if app:
            clauses.append("app = ?")
            params.append(app)
        if query:
            clauses.append(
                "(title LIKE ? ESCAPE '\\'"
                " OR source_path LIKE ? ESCAPE '\\'"
                " OR reason LIKE ? ESCAPE '\\')"
            )
            like = f"%{_escape_like(query)}%"
            params += [like, like, like]

        # Only the clause skeleton is interpolated; every value stays a bound param.
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        limit = max(1, min(limit, MAX_PAGE_SIZE))
        offset = max(0, offset)

        with self._lock:
            total = int(
                self._conn.execute(
                    f"SELECT COUNT(*) FROM operations{where}",  # noqa: S608
                    params,
                ).fetchone()[0]
            )
            rows = self._conn.execute(
                f"SELECT * FROM operations{where} ORDER BY id DESC LIMIT ? OFFSET ?",  # noqa: S608
                [*params, limit, offset],
            ).fetchall()

        return Page(
            items=[_to_operation(row) for row in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    def stats(self) -> Stats:
        cutoff = _iso(datetime.now(UTC) - timedelta(hours=24))
        with self._lock:
            total, muxed, recent = self._conn.execute(
                """
                SELECT
                    COUNT(*),
                    COALESCE(SUM(move_status != 'DeferMove'), 0),
                    COALESCE(SUM(created_at >= ?), 0)
                FROM operations
                """,
                (cutoff,),
            ).fetchone()
            added = self._conn.execute(
                "SELECT added_tracks FROM operations WHERE move_status != 'DeferMove'"
            ).fetchall()

        tracks = sum(len(json.loads(row[0] or "[]")) for row in added)
        return Stats(
            total=int(total),
            muxed=int(muxed),
            deferred=int(total) - int(muxed),
            tracks_added=tracks,
            last_24h=int(recent),
        )

    def clear(self) -> int:
        with self._lock:
            cursor = self._conn.execute("DELETE FROM operations")
            self._conn.commit()
            return cursor.rowcount


def _now() -> str:
    return _iso(datetime.now(UTC))


def _escape_like(value: str) -> str:
    """Neutralise LIKE wildcards so a search for "%" matches a literal percent."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _iso(moment: datetime) -> str:
    return moment.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _to_operation(row: sqlite3.Row) -> Operation:
    return Operation(
        id=int(row["id"]),
        created_at=str(row["created_at"]),
        app=str(row["app"]),
        title=str(row["title"]),
        move_status=str(row["move_status"]),
        reason=str(row["reason"]),
        source_path=str(row["source_path"]),
        destination_path=str(row["destination_path"]),
        media_file=row["media_file"],
        transfer_mode=str(row["transfer_mode"]),
        season=row["season"],
        episodes=[int(e) for e in str(row["episodes"]).split(",") if e.strip()],
        added_tracks=list(json.loads(row["added_tracks"] or "[]")),
        rejected_tracks=list(json.loads(row["rejected_tracks"] or "[]")),
        duration_ms=int(row["duration_ms"]),
        source_bytes=row["source_bytes"],
        output_bytes=row["output_bytes"],
        dry_run=bool(row["dry_run"]),
    )
