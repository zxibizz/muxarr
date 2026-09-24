"""Closed vocabularies shared across the layers.

Kept as ``Literal`` aliases rather than ``StrEnum``: every value crosses a JSON
or argv boundary as a bare string, and mypy already rejects a typo in either.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal, get_args

TrackKind = Literal["video", "audio", "subtitles"]

# ISO 639-2 "undetermined"; mkvmerge's own default for an untagged track.
UNDETERMINED = "und"

# A keep-list entry standing for the movie's or series' original language, as *arr
# reports it -- what Radarr calls "Original" in a language profile.
ORIGINAL_LANGUAGE = "original"

DedupeMode = Literal["off", "language", "language_codec"]
DEDUPE_MODES: tuple[DedupeMode, ...] = get_args(DedupeMode)

# How much of sidecar discovery an LLM is allowed to decide. "verify" is a shadow
# mode: the heuristic answer still wins, disagreements are only logged.
AiMode = Literal["off", "fallback", "always", "verify"]
AI_MODES: tuple[AiMode, ...] = get_args(AiMode)

# How a browser proves who it is. "external" trusts a reverse proxy in front.
AuthMethod = Literal["forms", "external"]
AUTH_METHODS: tuple[AuthMethod, ...] = get_args(AuthMethod)

AuthRequired = Literal["enabled", "disabled_for_local_addresses"]
AUTH_REQUIRED: tuple[AuthRequired, ...] = get_args(AuthRequired)

# Which processes one container runs; web and worker need a shared Postgres.
ContainerMode = Literal["all", "web", "worker"]
CONTAINER_MODES: tuple[ContainerMode, ...] = get_args(ContainerMode)

# Where a candidate track came from; surfaced in the history so a human can tell
# an inferred match from a filename-derived one.
TrackSource = Literal["heuristic", "ai"]

# The three verdicts Radarr/Sonarr understand on an import script's stdout.
MoveStatus = Literal["DeferMove", "MoveComplete", "RenameRequested"]

App = Literal["radarr", "sonarr"]

# Why a discovered sidecar was not embedded. Code keys off these, never the prose.
RejectCode = Literal[
    "image_subtitle",
    "undetermined_language",
    "language_not_kept",
    "already_present",
    "track_limit",
    "file_missing",
    "file_empty",
    "uninspectable",
    "no_tracks",
]

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
    # The composition root, which both processes build.
    CORE = "core"
    WORKER = "worker"

    USECASE_AUTH = "usecase.auth"
    USECASE_IMPORT = "usecase.import"
    USECASE_JOBS = "usecase.jobs"

    INFRA_AI = "infra.ai"
    INFRA_DISCOVERY = "infra.discovery"
    INFRA_JOBS = "infra.jobs"
    INFRA_MUX = "infra.mux"
    INFRA_PLACEMENT = "infra.placement"
    INFRA_PROBE = "infra.probe"
    INFRA_PROCESS = "infra.process"
    INFRA_SETTINGS = "infra.settings"
