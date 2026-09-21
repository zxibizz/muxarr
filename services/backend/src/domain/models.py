"""Persistent models.

``created_at`` is a TEXT ISO-8601 timestamp rather than a DATETIME: the value is
handed to the API verbatim, and SQLite has no native date type to gain from.
``episodes`` is comma-joined and the track lists are JSON, both carried over
unchanged from the pre-SQLAlchemy schema so the first migration is a faithful
port of an existing table.
"""

from __future__ import annotations

from sqlalchemy import Index, Integer, Text
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
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    source_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dry_run: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
