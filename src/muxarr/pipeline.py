"""The import decision table.

This is where Radarr/Sonarr semantics live. Every path through it ends in one of
three answers, and every unexpected condition ends in ``DeferMove`` -- the answer
that makes *arr perform a completely normal import as though muxarr were absent.

The source folder is never written to, in any transfer mode.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from muxarr import discovery, probe, selection
from muxarr.config import Settings
from muxarr.discovery import EpisodeRef
from muxarr.errors import MuxarrError
from muxarr.models import ExternalTrack, MediaInfo
from muxarr.mux import MuxPlan, run_mux
from muxarr.paths import PathGuard, is_within, resolve
from muxarr.placement import (
    PlacementPolicy,
    copy_attributes,
    ensure_free_space,
    finalise,
    staged_output,
)

log = logging.getLogger(__name__)

MoveStatus = Literal["DeferMove", "MoveComplete", "RenameRequested"]
App = Literal["radarr", "sonarr"]

OUTPUT_SUFFIX = ".mkv"


@dataclass(frozen=True, slots=True)
class ImportRequest:
    app: App
    source_path: Path
    destination_path: Path
    # Radarr_Movie_Path / Sonarr_Series_Path. Used for the re-entrancy guard.
    library_path: Path
    transfer_mode: str = "Move"
    season: int | None = None
    episodes: tuple[int, ...] = ()
    dry_run: bool = False

    @property
    def episode_ref(self) -> EpisodeRef | None:
        if self.season is None:
            return None
        return EpisodeRef(season=self.season, episodes=self.episodes)


@dataclass(frozen=True, slots=True)
class ImportOutcome:
    move_status: MoveStatus
    reason: str
    media_file: Path | None = None
    extra_files: tuple[Path, ...] = ()
    prevent_extra_import: bool = False
    added_tracks: tuple[str, ...] = ()
    # Why each discovered sidecar was passed over; the history UI shows these.
    rejected_tracks: tuple[dict[str, str], ...] = ()
    duration_ms: int = 0
    source_bytes: int | None = None
    output_bytes: int | None = None

    @property
    def deferred(self) -> bool:
        return self.move_status == "DeferMove"


def _defer(reason: str, **extra: object) -> ImportOutcome:
    log.info("deferring to native import: %s", reason)
    return ImportOutcome(move_status="DeferMove", reason=reason, **extra)  # type: ignore[arg-type]


def handle_import(
    request: ImportRequest,
    settings: Settings,
    guard: PathGuard | None = None,
) -> ImportOutcome:
    """Decide what to do with one import, and do it.

    Never raises for an expected failure; callers translate the outcome directly
    into muxarr's stdout protocol.
    """
    started = time.monotonic()
    outcome = _decide(request, settings, guard)
    return replace(
        outcome,
        duration_ms=int((time.monotonic() - started) * 1000),
        source_bytes=_size_of(request.source_path),
        output_bytes=_size_of(outcome.media_file),
    )


def _size_of(path: Path | None) -> int | None:
    if path is None:
        return None
    try:
        return path.stat().st_size
    except OSError:
        return None


def _decide(
    request: ImportRequest,
    settings: Settings,
    guard: PathGuard | None = None,
) -> ImportOutcome:
    guard = guard or PathGuard.from_roots(settings.read_roots)

    try:
        source = guard.check_read(request.source_path)
        library = guard.check_read(request.library_path)
        destination = guard.check_destination(request.destination_path)
    except MuxarrError as exc:
        return _defer(f"path rejected: {exc}")

    # Second invocation: RenameRequested makes *arr call the script again with our
    # own output as the source. Without this the mux would recurse.
    if is_within(source, library):
        return _defer("source is already inside the library; nothing to do")

    if not source.is_file():
        return _defer(f"source does not exist: {source}")

    try:
        info = probe.probe(source)
    except MuxarrError as exc:
        return _defer(f"could not probe source: {exc}")

    candidates = discovery.discover(source, episode=request.episode_ref)
    if not candidates:
        return _defer("no external tracks found beside the source")

    chosen = selection.select(info, candidates, settings.selection_policy)
    rejections = tuple(
        {"track": t.path.name, "reason": why} for t, why in chosen.rejected
    )
    if not chosen.accepted:
        reasons = "; ".join(f"{r['track']}: {r['reason']}" for r in rejections)
        return _defer(
            f"nothing worth embedding ({reasons or 'no candidates'})",
            rejected_tracks=rejections,
        )

    output = destination.with_suffix(OUTPUT_SUFFIX)
    try:
        guard.check_destination(output)
    except MuxarrError as exc:
        return _defer(f"output path rejected: {exc}", rejected_tracks=rejections)

    descriptions = tuple(_describe(t) for t in chosen.accepted)

    if request.dry_run:
        return ImportOutcome(
            move_status="DeferMove",
            reason="dry run",
            added_tracks=descriptions,
            rejected_tracks=rejections,
        )

    policy = PlacementPolicy(
        scratch_dir=settings.scratch_dir,
        free_space_factor=settings.free_space_factor,
        preserve_ownership=settings.preserve_ownership,
    )

    try:
        _ensure_room(source, chosen.accepted, output, policy)
        _mux_into_place(request, info, chosen.accepted, output, settings, policy)
    except MuxarrError as exc:
        return _defer(
            f"mux failed, leaving the import to *arr: {exc}",
            added_tracks=descriptions,
            rejected_tracks=rejections,
        )

    log.info("embedded %d track(s) into %s", len(descriptions), output)
    return ImportOutcome(
        move_status="RenameRequested",
        reason=f"embedded {len(descriptions)} external track(s)",
        media_file=output,
        # Hand back the sidecars we did not embed so they are not silently lost.
        extra_files=tuple(t.path for t, _ in chosen.rejected if t.kind == "subtitles"),
        prevent_extra_import=True,
        added_tracks=descriptions,
        rejected_tracks=rejections,
    )


def _ensure_room(
    source: Path,
    tracks: Sequence[ExternalTrack],
    output: Path,
    policy: PlacementPolicy,
) -> None:
    required = source.stat().st_size + sum(t.path.stat().st_size for t in tracks)
    ensure_free_space(output.parent, required, factor=policy.free_space_factor)


def _mux_into_place(
    request: ImportRequest,
    info: MediaInfo,
    tracks: Sequence[ExternalTrack],
    output: Path,
    settings: Settings,
    policy: PlacementPolicy,
) -> None:
    modern = probe.supports_modern_flag_syntax(probe.mkvmerge_version())

    with staged_output(output, policy) as staging:
        plan = MuxPlan(
            source=resolve(request.source_path),
            output=staging,
            tracks=tuple(tracks),
            modern_flags=modern,
            sub_charset=settings.sub_charset,
        )
        run_mux(plan, info, timeout=settings.mux_timeout_seconds)
        finalise(staging, output, policy)

    copy_attributes(resolve(request.source_path), output, policy)


def _describe(track: ExternalTrack) -> str:
    label = track.name or track.language
    return f"{track.kind}:{label}"
