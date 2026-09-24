"""History wire models."""

from __future__ import annotations

from dataclasses import asdict
from typing import cast

from pydantic import Field

from src.application.interfaces.history import OperationRecord
from src.domain.enums import App, MoveStatus
from src.schemas.arr import ArrModel
from src.schemas.base import WireModel
from src.schemas.journal import LogEntryModel, RejectedTrackModel, RemovedTrackModel, TrackModel


class OperationModel(WireModel):
    id: int
    created_at: str
    app: App
    title: str
    move_status: MoveStatus
    reason: str
    source_path: str
    destination_path: str
    media_file: str | None = None
    transfer_mode: str = ""
    season: int | None = None
    episodes: list[int] = Field(default_factory=list)
    added_tracks: list[TrackModel] = Field(default_factory=list)
    rejected_tracks: list[RejectedTrackModel] = Field(default_factory=list)
    removed_tracks: list[RemovedTrackModel] = Field(default_factory=list)
    log: list[LogEntryModel] = Field(default_factory=list)
    duration_ms: int = 0
    source_bytes: int | None = None
    output_bytes: int | None = None
    dry_run: bool = False
    arr: ArrModel | None = None

    @classmethod
    def from_record(cls, record: OperationRecord) -> OperationModel:
        fields = asdict(record)
        fields["arr"] = ArrModel.from_context(cast("App", record.app), record.arr)
        return cls(**fields)


class HistoryPage(WireModel):
    items: list[OperationModel]
    total: int
    limit: int
    offset: int


class StatsModel(WireModel):
    total: int
    muxed: int
    deferred: int
    tracks_added: int
    last_24h: int


class ClearedModel(WireModel):
    deleted: int
