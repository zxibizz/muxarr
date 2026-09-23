"""Persistent models.

``created_at`` is a TEXT ISO-8601 timestamp rather than a DATETIME: the value is
handed to the API verbatim, and SQLite has no native date type to gain from.
``episodes`` is comma-joined and the track lists are JSON, both carried over
unchanged from the pre-SQLAlchemy schema so the first migration is a faithful
port of an existing table.
"""

from __future__ import annotations

from sqlalchemy import Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.db import Base


class Operation(Base):
    """One import decision, including the ones that deferred."""

    __tablename__ = "operations"
    __table_args__ = (
        Index("idx_operations_created", "created_at"),
        Index("idx_operations_status", "move_status"),
        Index("idx_operations_app", "app"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    app: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    move_status: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    source_path: Mapped[str] = mapped_column(Text, nullable=False)
    destination_path: Mapped[str] = mapped_column(Text, nullable=False)
    media_file: Mapped[str | None] = mapped_column(Text, nullable=True)
    transfer_mode: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    season: Mapped[int | None] = mapped_column(Integer, nullable=True)
    episodes: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    added_tracks: Mapped[str] = mapped_column(Text, nullable=False, server_default="[]")
    rejected_tracks: Mapped[str] = mapped_column(Text, nullable=False, server_default="[]")
    # The source's own tracks the keep lists stripped, as JSON.
    removed_tracks: Mapped[str] = mapped_column(Text, nullable=False, server_default="[]")
    # Every log record the import emitted, as JSON. Rows written before this
    # column existed keep the empty list and render as "no log recorded".
    log: Mapped[str] = mapped_column(Text, nullable=False, server_default="[]")
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    source_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dry_run: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


class Job(Base):
    """One queued or completed import, handed from the API to the worker.

    The id is supplied by the shim so a retried submission re-attaches to the
    running mux instead of starting a second one.
    """

    __tablename__ = "jobs"
    __table_args__ = (Index("idx_jobs_state_created", "state", "created_at"),)

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    # Digest of the request, so a reused id carrying a different import is a 409.
    fingerprint: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")

    app: Mapped[str] = mapped_column(Text, nullable=False)
    source_path: Mapped[str] = mapped_column(Text, nullable=False)
    destination_path: Mapped[str] = mapped_column(Text, nullable=False)
    transfer_mode: Mapped[str] = mapped_column(Text, nullable=False, server_default="Move")
    dry_run: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    outcome: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    history_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # The same log the operation ends up with, flushed while the job is still
    # running so the UI can follow it. This copy dies with the job's TTL; the
    # operation keeps the durable one.
    log: Mapped[str] = mapped_column(Text, nullable=False, server_default="[]")

    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)


class WorkerState(Base):
    """Single row; the worker's liveness as seen by the API process."""

    __tablename__ = "worker_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    last_seen: Mapped[str] = mapped_column(Text, nullable=False)


class AppSettings(Base):
    """Single row; the UI-edited overrides layered over the environment.

    One row rather than a key per row so a save is atomic, and so ``revision``
    is a single integer the worker process can cheaply poll for changes.
    ``payload`` holds only the overridden keys, as the same raw strings the
    environment would have supplied.
    """

    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    payload: Mapped[str] = mapped_column(Text, nullable=False, server_default="{}")
    revision: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)
