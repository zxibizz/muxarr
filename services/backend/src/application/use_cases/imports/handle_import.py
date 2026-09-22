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
from src.domain.journal import LogStage, RejectedTrack, TrackDetail
from src.domain.media import ExternalTrack, MediaInfo
from src.domain.paths import PathGuard, resolve
from src.settings.config import Settings

log = get_logger(LogComponent.USECASE_IMPORT)


def _note(stage: LogStage, message: str, **context: object) -> None:
    """Log a line that is also a step of this import's story.

    The stage is what lets the UI replay the decision as a narrative, and it
    costs nothing extra: the same record still goes to stdout. Context is bound
    rather than passed as kwargs because these messages carry filenames, and a
    brace in one would otherwise be read as a format placeholder.
    """
    log.bind(stage=stage.value, **context).info(message)


def _defer(reason: str, *, stage: LogStage = LogStage.OUTCOME, **extra: object) -> ImportOutcome:
    _note(stage, f"deferring to *arr: {reason}")
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
            return _defer(f"path rejected: {exc}", stage=LogStage.GUARD)

        _note(
            LogStage.GUARD,
            "paths accepted",
            source=source,
            destination=destination,
            mode=request.transfer_mode,
        )

        if not source.is_file():
            return _defer(f"source does not exist: {source}", stage=LogStage.GUARD)

        try:
            info = self._prober.probe(source)
        except MuxarrError as exc:
            return _defer(f"could not probe source: {exc}", stage=LogStage.PROBE)

        _note(LogStage.PROBE, f"source already holds {_inventory(info)}", container=info.container)
        for existing in info.tracks:
            if existing.kind != "video":
                log.bind(
                    codec=existing.codec_family,
                    name=existing.name,
                    forced=existing.forced,
                ).debug(f"existing {existing.kind} track: {existing.language}")

        candidates = self._tracks.discover(source, episode=request.episode_ref)
        if not candidates:
            return _defer("no external tracks found beside the source", stage=LogStage.DISCOVERY)

        by_ai = sum(1 for c in candidates if c.source == "ai")
        _note(
            LogStage.DISCOVERY,
            f"found {len(candidates)} sidecar file(s) worth considering",
            identified_by_ai=by_ai,
        )

        policy = settings.selection_policy
        _note(
            LogStage.SELECTION,
            f"comparing against the container, de-duplicating by {policy.dedupe}",
            max_tracks=policy.max_external_tracks,
            skip_image_subtitles=policy.skip_image_subtitles,
            skip_undetermined=policy.skip_undetermined_language,
        )
        chosen = selection.select(info, candidates, policy)
        for track in chosen.accepted:
            _note(
                LogStage.SELECTION,
                f"embedding {_summarise(track)}, {_origin(track)}",
                file=track.path.name,
            )
        for track, why in chosen.rejected:
            _note(
                LogStage.SELECTION,
                f"skipping {_summarise(track)}: {why}",
                file=track.path.name,
            )

        rejections = tuple(_rejection(t, why) for t, why in chosen.rejected)
        if not chosen.accepted:
            reasons = "; ".join(f"{r.track}: {r.reason}" for r in rejections)
            return _defer(
                f"nothing worth embedding ({reasons or 'no candidates'})",
                rejected_tracks=rejections,
            )

        output = destination.with_suffix(OUTPUT_SUFFIX)
        try:
            guard.check_destination(output)
        except MuxarrError as exc:
            return _defer(
                f"output path rejected: {exc}",
                stage=LogStage.GUARD,
                rejected_tracks=rejections,
            )

        details = tuple(_detail(t) for t in chosen.accepted)

        if request.dry_run:
            return _defer(
                "dry run",
                added_tracks=details,
                rejected_tracks=rejections,
            )

        placement = PlacementPolicy(
            scratch_dir=settings.scratch_dir,
            free_space_factor=settings.free_space_factor,
            preserve_ownership=settings.preserve_ownership,
        )

        try:
            self._ensure_room(source, chosen.accepted, output, placement)
            _note(LogStage.MUX, f"remuxing into {output.name}", tracks=len(details))
            self._mux_into_place(request, info, chosen.accepted, output, placement)
        except MuxarrError as exc:
            return _defer(
                f"mux failed, leaving the import to *arr: {exc}",
                stage=LogStage.MUX,
                added_tracks=details,
                rejected_tracks=rejections,
            )

        _note(LogStage.OUTCOME, f"embedded {len(details)} external track(s)", output=output)
        return ImportOutcome(
            move_status="RenameRequested",
            reason=f"embedded {len(details)} external track(s)",
            media_file=output,
            # Hand back the sidecars we did not embed so they are not silently lost.
            extra_files=tuple(t.path for t, _ in chosen.rejected if t.kind == "subtitles"),
            prevent_extra_import=True,
            added_tracks=details,
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


def _inventory(info: MediaInfo) -> str:
    counts = (
        f"{len(info.video)} video",
        f"{len(info.audio)} audio",
        f"{len(info.subtitles)} subtitle",
    )
    return ", ".join(counts) + " track(s)"


def _summarise(track: ExternalTrack) -> str:
    flags = [f for f, on in (("forced", track.forced), ("SDH", track.hearing_impaired)) if on]
    if track.variant:
        flags.append(track.variant)
    label = track.name or track.language
    suffix = f" ({', '.join(flags)})" if flags else ""
    return f"{track.kind} {label} [{track.language}]{suffix} from {track.path.name}"


def _origin(track: ExternalTrack) -> str:
    if track.source == "ai":
        return "identified by the AI provider"
    return "identified from its filename"


def _detail(track: ExternalTrack) -> TrackDetail:
    return TrackDetail(
        kind=track.kind,
        label=track.name or track.language,
        language=track.language,
        name=track.name,
        forced=track.forced,
        hearing_impaired=track.hearing_impaired,
        variant=track.variant,
        file=track.path.name,
        source=track.source,
    )


def _rejection(track: ExternalTrack, reason: str) -> RejectedTrack:
    return RejectedTrack(
        track=track.path.name,
        reason=reason,
        kind=track.kind,
        language=track.language,
        source=track.source,
    )
