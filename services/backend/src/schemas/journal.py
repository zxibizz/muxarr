"""Wire models for what an import did.

Shared by the history and the job views: a running job and the operation it
becomes show the same log, so the shape has to be the same one.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.domain.enums import UNDETERMINED, TrackKind, TrackSource


class TrackModel(BaseModel):
    kind: TrackKind = "subtitles"
    label: str = ""
    language: str = UNDETERMINED
    name: str | None = None
    forced: bool = False
    hearing_impaired: bool = False
    variant: str | None = None
    file: str = ""
    source: TrackSource = "heuristic"


class RejectedTrackModel(BaseModel):
    track: str
    reason: str
    kind: TrackKind = "subtitles"
    language: str = UNDETERMINED
    source: TrackSource = "heuristic"


class LogEntryModel(BaseModel):
    ts: str
    level: str
    component: str
    message: str
    # Set on the records that make up the narrative; null on the rest.
    stage: str | None = None
    context: dict[str, str] = Field(default_factory=dict)
