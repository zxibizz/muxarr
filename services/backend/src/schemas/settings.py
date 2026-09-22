"""Settings wire models.

The AI key is write-only: ``SettingsView`` reports only whether one is set, so
a token pasted into the browser can never be read back out of it.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from src.domain.enums import AiMode, DedupeMode
from src.settings.config import MAX_OPERATION_LOG_ENTRIES

LogLevel = Literal["TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"]


class SettingsView(BaseModel):
    dedupe: DedupeMode
    skip_image_subtitles: bool
    skip_undetermined_language: bool
    max_external_tracks: int
    sub_charset: str | None

    mux_timeout_seconds: float
    free_space_factor: float
    preserve_ownership: bool

    max_concurrent_muxes: int
    job_ttl_seconds: float
    history_max_records: int
    operation_log_max_entries: int

    ai_mode: AiMode
    ai_base_url: str
    ai_model: str
    ai_timeout_seconds: float
    ai_max_entries: int
    ai_name_tracks: bool
    ai_api_key_set: bool

    log_level: str

    # Pinned by an environment variable; the UI renders these read-only.
    locked: list[str]


class SettingsPatch(BaseModel):
    """Only the fields actually sent are changed."""

    model_config = {"extra": "forbid"}

    dedupe: DedupeMode | None = None
    skip_image_subtitles: bool | None = None
    skip_undetermined_language: bool | None = None
    max_external_tracks: int | None = Field(default=None, ge=1)
    sub_charset: str | None = None

    mux_timeout_seconds: float | None = Field(default=None, ge=1)
    free_space_factor: float | None = Field(default=None, ge=1)
    preserve_ownership: bool | None = None

    max_concurrent_muxes: int | None = Field(default=None, ge=1)
    job_ttl_seconds: float | None = Field(default=None, ge=60)
    history_max_records: int | None = Field(default=None, ge=1)
    operation_log_max_entries: int | None = Field(
        default=None, ge=0, le=MAX_OPERATION_LOG_ENTRIES
    )

    ai_mode: AiMode | None = None
    ai_base_url: str | None = None
    # Absent leaves the stored key alone; null or "" clears it.
    ai_api_key: str | None = None
    ai_model: str | None = None
    ai_timeout_seconds: float | None = Field(default=None, ge=1)
    ai_max_entries: int | None = Field(default=None, ge=1)
    ai_name_tracks: bool | None = None

    log_level: LogLevel | None = None


class AiTestRequest(BaseModel):
    """Credentials as currently typed, so a key can be checked before saving."""

    base_url: str
    model: str
    # Omitted means "use the one already stored".
    api_key: str | None = None
    timeout_seconds: float = Field(default=10.0, ge=1)


class AiTestResult(BaseModel):
    ok: bool
    message: str
    latency_ms: int
