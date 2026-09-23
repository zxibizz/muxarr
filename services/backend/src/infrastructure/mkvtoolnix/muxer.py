"""Build and run the mkvmerge command.

Only stream-copy is performed: mkvmerge never re-encodes, so a mux costs one
sequential read of each input and one sequential write of the output.

If mkvmerge cannot read the source container the caller is expected to skip the
import entirely rather than fall back to a slower path -- ffmpeg would have to
rewrite the file too, and a source mkvmerge rejects is usually damaged.
"""

from __future__ import annotations

from src.application.interfaces.muxer import MuxPlan
from src.core.logging import get_logger
from src.domain.enums import LogComponent, TrackKind
from src.domain.errors import MuxError
from src.domain.media import ExternalTrack, MediaInfo
from src.infrastructure.mkvtoolnix.probe import (
    mkvmerge_version,
    probe_with_mkvmerge,
    supports_modern_flag_syntax,
)
from src.infrastructure.process.runner import CommandResult, resolve_tool, run

log = get_logger(LogComponent.INFRA_MUX)

# A remux is IO-bound on the file size; 4 hours is a generous ceiling for a
# large remux on slow storage while still bounding a hung process.
MUX_TIMEOUT = 4 * 60 * 60.0

MKVMERGE_WARNING_EXIT = 1

# mkvmerge's own prefixes for the lines that actually explain a bad mux.
_DIAGNOSTIC_PREFIXES = ("Warning:", "Error:")
# Per-percent progress lines; on a pipe they are one line each and bury everything.
_PROGRESS_PREFIX = "Progress:"


def diagnostics(result: CommandResult, lines: int = 10) -> str:
    """The interesting part of mkvmerge's output."""
    output = result.output_lines()
    flagged = [line for line in output if line.startswith(_DIAGNOSTIC_PREFIXES)]
    chosen = flagged or [line for line in output if not line.startswith(_PROGRESS_PREFIX)]
    return "\n".join(chosen[-lines:])


def build_argv(plan: MuxPlan, executable: str = "mkvmerge") -> list[str]:
    """Assemble the full mkvmerge argv.

    Per-file options must appear *before* the filename they apply to, and track
    selectors are relative to that file -- hence the ``0:`` prefixes, which target
    the first (and for a sidecar, only) track inside each external file.
    """
    argv: list[str] = [executable, "--output", str(plan.output)]

    if plan.title is not None:
        argv += ["--title", plan.title]

    argv += list(plan.extra_args)
    argv.append(str(plan.source))

    for track in plan.tracks:
        argv += _options_for(track, plan)
        argv.append(str(track.path))

    return argv


def _options_for(track: ExternalTrack, plan: MuxPlan) -> list[str]:
    options: list[str] = ["--language", f"0:{track.language}"]

    if track.name:
        options += ["--track-name", f"0:{track.name}"]

    if plan.sub_charset and track.kind == "subtitles":
        options += ["--sub-charset", f"0:{plan.sub_charset}"]

    # Added tracks never claim the default flag; hijacking playback order is a
    # worse failure than the user having to pick the track once.
    if plan.modern_flags:
        options += ["--default-track-flag", "0:0"]
        options += ["--forced-display-flag", f"0:{int(track.forced)}"]
        options += ["--hearing-impaired-flag", f"0:{int(track.hearing_impaired)}"]
    else:
        options += ["--default-track", "0:0"]
        options += ["--forced-track", f"0:{int(track.forced)}"]

    return options


def run_mux(
    plan: MuxPlan,
    source_info: MediaInfo,
    *,
    timeout: float = MUX_TIMEOUT,
) -> MediaInfo:
    """Execute the plan and verify the result. Raises :class:`MuxError` on failure."""
    if not plan.tracks:
        raise MuxError("refusing to mux with no external tracks")

    argv = build_argv(plan, resolve_tool("mkvmerge"))
    result = run(argv, timeout=timeout, deprioritise=True)

    if result.returncode == MKVMERGE_WARNING_EXIT:
        log.bind(output=plan.output).warning(f"mkvmerge warned: {diagnostics(result)}")
    elif not result.ok:
        raise MuxError(f"mkvmerge failed (exit {result.returncode}): {diagnostics(result, 20)}")

    if not plan.output.is_file():
        raise MuxError(f"mkvmerge reported success but produced no output at {plan.output}")

    log.bind(output=plan.output).debug("mkvmerge finished, verifying the result")
    return verify(plan, source_info)


def verify(plan: MuxPlan, source_info: MediaInfo) -> MediaInfo:
    """Re-probe the output and confirm every requested track landed."""
    info = probe_with_mkvmerge(plan.output)

    if not info.video:
        raise MuxError(f"muxed output has no video track: {plan.output}")

    kinds: tuple[TrackKind, ...] = ("audio", "subtitles")
    for kind in kinds:
        expected = sum(1 for t in plan.tracks if t.kind == kind)
        if expected == 0:
            continue
        landed = info.of_kind(kind)
        required = len(source_info.of_kind(kind)) + expected
        if len(landed) < required:
            # Name what did land: mkvmerge silently drops a sidecar it cannot read,
            # and the difference is the only way to tell which one.
            got = ", ".join(f"{t.language}/{t.name or '-'}" for t in landed) or "none"
            raise MuxError(
                f"expected at least {required} {kind} tracks in {plan.output}, "
                f"found {len(landed)} ({got})"
            )

    return info


class MkvmergeMuxer:
    """Adapter object for the container; delegates to the module functions."""

    def supports_modern_flags(self) -> bool:
        return supports_modern_flag_syntax(mkvmerge_version())

    def run(self, plan: MuxPlan, source_info: MediaInfo, *, timeout: float) -> MediaInfo:
        return run_mux(plan, source_info, timeout=timeout)
