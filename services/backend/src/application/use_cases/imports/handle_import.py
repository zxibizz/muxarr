"""The import decision table.

This is where Radarr/Sonarr semantics live. Every path through it ends in one of
three answers, and every unexpected condition ends in ``DeferMove`` -- the answer
that makes *arr perform a completely normal import as though muxarr were absent.

The source folder is never written to, in any transfer mode.

``execute`` is synchronous on purpose: a remux takes minutes to hours, so the API
runs it on a worker thread rather than blocking the event loop.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from src.application.interfaces.muxer import Muxer, MuxPlan
from src.application.interfaces.placement import Placement, PlacementPolicy
from src.application.interfaces.prober import MediaProber
from src.application.interfaces.track_source import TrackDiscovery
from src.application.use_cases.imports.dto import OUTPUT_SUFFIX, ImportOutcome, ImportRequest
from src.core.logging import get_logger
from src.domain import selection
from src.domain.enums import LogComponent
from src.domain.errors import MuxarrError
from src.domain.media import ExternalTrack, MediaInfo
from src.domain.paths import PathGuard, resolve
from src.settings.config import Settings

log = get_logger(LogComponent.USECASE_IMPORT)


def _defer(reason: str, **extra: object) -> ImportOutcome:
    log.info("deferring to native import", reason=reason)
    return ImportOutcome(move_status="DeferMove", reason=reason, **extra)  # type: ignore[arg-type]


class HandleImportUseCase:
    def __init__(
        self,
        *,
        settings: Settings,
        guard: PathGuard,
        prober: MediaProber,
        tracks: TrackDiscovery,
        muxer: Muxer,
        placement: Placement,
    ) -> None:
        self._settings = settings
        self._guard = guard
        self._prober = prober
        self._tracks = tracks
        self._muxer = muxer
        self._placement = placement

    def execute(self, request: ImportRequest) -> ImportOutcome:
        """Decide what to do with one import, and do it.

        Never raises for an expected failure; callers translate the outcome
        directly into muxarr's stdout protocol.
        """
        started = time.monotonic()
        outcome = self._decide(request)
        return replace(
            outcome,
            duration_ms=int((time.monotonic() - started) * 1000),
            source_bytes=_size_of(request.source_path),
            output_bytes=_size_of(outcome.media_file),
        )

    def _decide(self, request: ImportRequest) -> ImportOutcome:
        settings = self._settings
        guard = self._guard

        try:
            source = guard.check_read(request.source_path)
            destination = guard.check_destination(request.destination_path)
        except MuxarrError as exc:
            return _defer(f"path rejected: {exc}")

        if not source.is_file():
            return _defer(f"source does not exist: {source}")

        try:
            info = self._prober.probe(source)
        except MuxarrError as exc:
            return _defer(f"could not probe source: {exc}")

        candidates = self._tracks.discover(source, episode=request.episode_ref)
        if not candidates:
            return _defer("no external tracks found beside the source")

        chosen = selection.select(info, candidates, settings.selection_policy)
        rejections = tuple({"track": t.path.name, "reason": why} for t, why in chosen.rejected)
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
            self._ensure_room(source, chosen.accepted, output, policy)
            self._mux_into_place(request, info, chosen.accepted, output, policy)
        except MuxarrError as exc:
            return _defer(
                f"mux failed, leaving the import to *arr: {exc}",
                added_tracks=descriptions,
                rejected_tracks=rejections,
            )

        log.info("embedded external tracks", count=len(descriptions), output=output)
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
        self,
        source: Path,
        tracks: Sequence[ExternalTrack],
        output: Path,
        policy: PlacementPolicy,
    ) -> None:
        required = source.stat().st_size + sum(t.path.stat().st_size for t in tracks)
        self._placement.ensure_free_space(
            output.parent, required, factor=policy.free_space_factor
        )

    def _mux_into_place(
        self,
        request: ImportRequest,
        info: MediaInfo,
        tracks: Sequence[ExternalTrack],
        output: Path,
        policy: PlacementPolicy,
    ) -> None:
        modern = self._muxer.supports_modern_flags()

        with self._placement.staged_output(output, policy) as staging:
            plan = MuxPlan(
                source=resolve(request.source_path),
                output=staging,
                tracks=tuple(tracks),
                modern_flags=modern,
                sub_charset=self._settings.sub_charset,
            )
            self._muxer.run(plan, info, timeout=self._settings.mux_timeout_seconds)
            self._placement.finalise(staging, output, policy)

        self._placement.copy_attributes(resolve(request.source_path), output, policy)


def _size_of(path: Path | None) -> int | None:
    if path is None:
        return None
    try:
        return path.stat().st_size
    except OSError:
        return None


def _describe(track: ExternalTrack) -> str:
    label = track.name or track.language
    return f"{track.kind}:{label}"
