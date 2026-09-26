"""What muxarr did during one import, in a form a human can read.

Two shapes, both stored as JSON alongside the operation:

:class:`LogEntry` is one captured log record. An entry that carries a
:class:`LogStage` is also a step of the narrative -- the same line serves the
"what happened" summary and the raw trail, which is why a running job can show
its story before it has finished writing one.

:class:`TrackDetail` replaces the display string that used to be stored for an
embedded track. A string cannot say *why* a track looked the way it did, so the
UI had nothing better than an " [ai]" suffix to work with.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import get_args

from src.domain.enums import TRACK_SOURCES, UNDETERMINED, RejectCode, TrackKind, TrackSource


class LogStage(StrEnum):
    """The step of an import a log record belongs to.

    Closed, because the UI renders one timeline item per stage and an unknown
    value would simply vanish from it.
    """

    GUARD = "guard"
    PROBE = "probe"
    DISCOVERY = "discovery"
    AI = "ai"
    SELECTION = "selection"
    MUX = "mux"
    PLACEMENT = "placement"
    OUTCOME = "outcome"


_STAGES = frozenset(stage.value for stage in LogStage)
_REJECT_CODES: frozenset[str] = frozenset(get_args(RejectCode))


def _source(raw: object) -> TrackSource:
    for source in TRACK_SOURCES:
        if raw == source:
            return source
    return "heuristic"


@dataclass(frozen=True, slots=True)
class LogEntry:
    """One captured log record, as shown against a job or an operation."""

    ts: str
    level: str
    component: str
    message: str
    stage: str | None = None
    context: Mapping[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "ts": self.ts,
            "level": self.level,
            "component": self.component,
            "message": self.message,
            "stage": self.stage,
            "context": dict(self.context),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> LogEntry:
        stage = payload.get("stage")
        context = payload.get("context")
        return cls(
            ts=str(payload.get("ts", "")),
            level=str(payload.get("level", "INFO")),
            component=str(payload.get("component", "")),
            message=str(payload.get("message", "")),
            stage=str(stage) if isinstance(stage, str) and stage in _STAGES else None,
            context=(
                {str(k): str(v) for k, v in context.items()} if isinstance(context, Mapping) else {}
            ),
        )


@dataclass(frozen=True, slots=True)
class TrackDetail:
    """One embedded track, described well enough to explain itself."""

    kind: TrackKind
    label: str
    language: str = UNDETERMINED
    name: str | None = None
    forced: bool = False
    hearing_impaired: bool = False
    variant: str | None = None
    file: str = ""
    source: TrackSource = "heuristic"

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "label": self.label,
            "language": self.language,
            "name": self.name,
            "forced": self.forced,
            "hearing_impaired": self.hearing_impaired,
            "variant": self.variant,
            "file": self.file,
            "source": self.source,
        }

    @classmethod
    def from_stored(cls, payload: object) -> TrackDetail:
        """Rebuild from a stored value, tolerating rows written before this existed.

        Those hold a display string such as ``"subtitles:Russian [ai]"``.
        """
        if isinstance(payload, str):
            return cls._from_legacy(payload)
        if not isinstance(payload, Mapping):
            return cls(kind="subtitles", label=str(payload))
        kind = payload.get("kind")
        source = payload.get("source")
        return cls(
            kind=kind if kind in ("video", "audio", "subtitles") else "subtitles",
            label=str(payload.get("label", "")),
            language=str(payload.get("language", UNDETERMINED)),
            name=_optional_str(payload.get("name")),
            forced=bool(payload.get("forced", False)),
            hearing_impaired=bool(payload.get("hearing_impaired", False)),
            variant=_optional_str(payload.get("variant")),
            file=str(payload.get("file", "")),
            source=_source(source),
        )

    @classmethod
    def _from_legacy(cls, value: str) -> TrackDetail:
        text, ai = (value[: -len(" [ai]")], True) if value.endswith(" [ai]") else (value, False)
        kind, _, label = text.partition(":")
        if kind not in ("video", "audio", "subtitles"):
            kind, label = "subtitles", text
        return cls(
            kind=kind,  # type: ignore[arg-type]
            label=label,
            source="ai" if ai else "heuristic",
        )


@dataclass(frozen=True, slots=True)
class RejectedTrack:
    """A sidecar that was found but not embedded, and the reason why."""

    track: str
    reason: str
    kind: TrackKind = "subtitles"
    language: str = UNDETERMINED
    source: TrackSource = "heuristic"
    # None on rows written before codes existed.
    code: RejectCode | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "track": self.track,
            "reason": self.reason,
            "kind": self.kind,
            "language": self.language,
            "source": self.source,
            "code": self.code,
        }

    @classmethod
    def from_stored(cls, payload: object) -> RejectedTrack:
        if not isinstance(payload, Mapping):
            return cls(track=str(payload), reason="")
        kind = payload.get("kind")
        source = payload.get("source")
        code = payload.get("code")
        return cls(
            track=str(payload.get("track", "")),
            reason=str(payload.get("reason", "")),
            kind=kind if kind in ("video", "audio", "subtitles") else "subtitles",
            language=str(payload.get("language", UNDETERMINED)),
            source=_source(source),
            code=code if code in _REJECT_CODES else None,
        )


@dataclass(frozen=True, slots=True)
class RemovedTrack:
    """A track the source already held that the keep lists stripped from the output."""

    index: int
    kind: TrackKind
    language: str = UNDETERMINED
    name: str | None = None
    codec: str = ""
    forced: bool = False
    reason: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "kind": self.kind,
            "language": self.language,
            "name": self.name,
            "codec": self.codec,
            "forced": self.forced,
            "reason": self.reason,
        }

    @classmethod
    def from_stored(cls, payload: object) -> RemovedTrack:
        if not isinstance(payload, Mapping):
            return cls(index=-1, kind="subtitles", reason=str(payload))
        kind = payload.get("kind")
        index = payload.get("index")
        return cls(
            index=index if isinstance(index, int) else -1,
            kind=kind if kind in ("video", "audio", "subtitles") else "subtitles",
            language=str(payload.get("language", UNDETERMINED)),
            name=_optional_str(payload.get("name")),
            codec=str(payload.get("codec", "")),
            forced=bool(payload.get("forced", False)),
            reason=str(payload.get("reason", "")),
        )


def _optional_str(value: object) -> str | None:
    return str(value) if isinstance(value, str) and value else None


__all__ = ["LogEntry", "LogStage", "RejectedTrack", "RemovedTrack", "TrackDetail"]
