"""Wire models for what an import did.

Shared by the history and the job views: a running job and the operation it
becomes show the same log, so the shape has to be the same one.
"""

from __future__ import annotations

from pydantic import Field

from src.domain.enums import UNDETERMINED, RejectCode, TrackKind, TrackSource
from src.domain.journal import LogStage
from src.schemas.base import WireModel


class TrackModel(WireModel):
    kind: TrackKind = "subtitles"
    label: str = ""
    language: str = UNDETERMINED
    name: str | None = None
    forced: bool = False
    hearing_impaired: bool = False
    variant: str | None = None
    file: str = ""
    source: TrackSource = "heuristic"


class RejectedTrackModel(WireModel):
    track: str
    reason: str
    kind: TrackKind = "subtitles"
    language: str = UNDETERMINED
    source: TrackSource = "heuristic"
    code: RejectCode | None = None


class RemovedTrackModel(WireModel):
    index: int
    kind: TrackKind = "subtitles"
    language: str = UNDETERMINED
    name: str | None = None
    codec: str = ""
    forced: bool = False
    reason: str = ""


class LogEntryModel(WireModel):
    ts: str
    level: str
    component: str
    message: str
    # Set on the records that make up the narrative; null on the rest.
    stage: LogStage | None = None
    context: dict[str, str] = Field(default_factory=dict)
