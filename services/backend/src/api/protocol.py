"""Render an outcome as Radarr/Sonarr's import-script stdout protocol.

*arr parses each stdout line with one anchored regex and **silently ignores
anything that does not match**. A dropped ``[MoveStatus]`` line falls back to
``MoveComplete``, which tells *arr the file was moved when it was not -- so the
formatting here is load-bearing, and is pinned by tests against the regex copied
verbatim from ScriptImportDecider.cs.
"""

from __future__ import annotations

from src.application.use_cases.imports.dto import ImportOutcome

MEDIA_FILE = "[MediaFile]"
EXTRA_FILE = "[ExtraFile]"
PREVENT_EXTRA_IMPORT = "[PreventExtraImport]"
MOVE_STATUS = "[MoveStatus]"

DEFER = f"{MOVE_STATUS} DeferMove"

# Job state for the polling shim. Never reaches *arr: the shim strips it, and
# *arr would ignore it anyway since it does not match the protocol regex.
MUXARR_STATE = "[MuxarrState]"

STATE_RUNNING = "running"
STATE_DONE = "done"
STATE_ERROR = "error"
STATE_UNKNOWN = "unknown"


def render(outcome: ImportOutcome) -> list[str]:
    """Protocol lines for one outcome, in the order *arr should see them."""
    if outcome.deferred:
        # Deliberately nothing else: a MediaFile line alongside DeferMove would
        # point *arr's bookkeeping at a file it is not about to move.
        return [DEFER]

    lines: list[str] = []
    if outcome.media_file is not None:
        lines.append(f"{MEDIA_FILE} {outcome.media_file}")
    for extra in outcome.extra_files:
        lines.append(f"{EXTRA_FILE} {extra}")
    if outcome.prevent_extra_import:
        lines.append(PREVENT_EXTRA_IMPORT)
    lines.append(f"{MOVE_STATUS} {outcome.move_status}")
    return lines


def render_text(outcome: ImportOutcome) -> str:
    """Newline-terminated body. Never CRLF: a trailing \\r breaks the regex anchor."""
    return "".join(f"{line}\n" for line in render(outcome))


def render_poll(state: str, outcome: ImportOutcome | None = None) -> str:
    """Long-poll body: a state line, plus protocol lines once the mux is done."""
    body = f"{MUXARR_STATE} {state}\n"
    if outcome is not None:
        body += render_text(outcome)
    return body
