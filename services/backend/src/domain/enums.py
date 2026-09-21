"""Closed vocabularies shared across the layers.

Kept as ``Literal`` aliases rather than ``StrEnum``: every value crosses a JSON
or argv boundary as a bare string, and mypy already rejects a typo in either.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

TrackKind = Literal["video", "audio", "subtitles"]

# ISO 639-2 "undetermined"; mkvmerge's own default for an untagged track.
UNDETERMINED = "und"

DedupeMode = Literal["off", "language", "language_codec"]

# The three verdicts Radarr/Sonarr understand on an import script's stdout.
MoveStatus = Literal["DeferMove", "MoveComplete", "RenameRequested"]

App = Literal["radarr", "sonarr"]

JobState = Literal["pending", "running", "succeeded", "failed"]

TERMINAL_JOB_STATES: frozenset[str] = frozenset({"succeeded", "failed"})


class LogComponent(StrEnum):
    """Which part of the codebase wrote a log record.

    Closed rather than free-form so a mistyped component fails a type check
    instead of silently fragmenting the filter. The dotted prefix groups a
    layer: everything under ``infra.`` is an adapter talking to the outside.
    """

    API = "api"
    CLI = "cli"
    WORKER = "worker"

    USECASE_IMPORT = "usecase.import"
    USECASE_JOBS = "usecase.jobs"

    INFRA_DISCOVERY = "infra.discovery"
    INFRA_JOBS = "infra.jobs"
    INFRA_MUX = "infra.mux"
    INFRA_PLACEMENT = "infra.placement"
    INFRA_PROBE = "infra.probe"
    INFRA_PROCESS = "infra.process"
