"""Import and job wire models."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from src.application.interfaces.jobs import Job
from src.application.use_cases.imports.dto import ImportOutcome, ImportRequest
from src.infrastructure.jobs.memory_store import fingerprint

# Constrained so a job id cannot smuggle path separators into the URL or control
# characters into the log.
JOB_ID_PATTERN = r"^[A-Za-z0-9._:-]{8,128}$"


class ImportPayload(BaseModel):
    job_id: str = Field(pattern=JOB_ID_PATTERN)
    app: Literal["radarr", "sonarr"]
    source_path: str
    destination_path: str
    transfer_mode: str = "Move"
    dry_run: bool = False

    def to_request(self) -> ImportRequest:
        return ImportRequest(
            app=self.app,
            source_path=Path(self.source_path),
            destination_path=Path(self.destination_path),
            transfer_mode=self.transfer_mode,
            dry_run=self.dry_run,
        )

    def fingerprint(self) -> str:
        return fingerprint(self.model_dump(exclude={"job_id"}))


class ImportResult(BaseModel):
    move_status: str
    reason: str
    media_file: str | None = None
    extra_files: list[str] = Field(default_factory=list)
    prevent_extra_import: bool = False
    added_tracks: list[str] = Field(default_factory=list)

    @classmethod
    def from_outcome(cls, outcome: ImportOutcome) -> ImportResult:
        return cls(
            move_status=outcome.move_status,
            reason=outcome.reason,
            media_file=str(outcome.media_file) if outcome.media_file else None,
            extra_files=[str(p) for p in outcome.extra_files],
            prevent_extra_import=outcome.prevent_extra_import,
            added_tracks=list(outcome.added_tracks),
        )


class JobModel(BaseModel):
    id: str
    state: str
    result: ImportResult | None = None
    error: str | None = None
    history_id: int | None = None

    @classmethod
    def from_job(cls, job: Job) -> JobModel:
        return cls(
            id=job.id,
            state=job.state,
            result=ImportResult.from_outcome(job.outcome) if job.outcome else None,
            error=job.error,
            history_id=job.history_id,
        )
