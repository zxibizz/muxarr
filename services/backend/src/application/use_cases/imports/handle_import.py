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
from dataclasses import dataclass, replace
from pathlib import Path

from src.application.interfaces.muxer import Muxer, MuxPlan
from src.application.interfaces.placement import Placement, PlacementPolicy
from src.application.interfaces.prober import MediaProber
from src.application.interfaces.track_source import TrackDiscovery
from src.application.use_cases.imports.dto import OUTPUT_SUFFIX, ImportOutcome, ImportRequest
from src.core.logging import get_logger
from src.domain import selection
from src.domain.enums import LogComponent, RejectCode, TrackKind
from src.domain.errors import MuxarrError
from src.domain.journal import LogStage, RejectedTrack, RemovedTrack, TrackDetail
from src.domain.media import ExternalTrack, MediaInfo, Track
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


class _DeferError(Exception):
    """Unwinds the pipeline to a DeferMove. Caught in ``_decide``; never escapes it."""

    def __init__(self, reason: str, stage: LogStage = LogStage.OUTCOME) -> None:
        super().__init__(reason)
        self.reason = reason
        self.stage = stage


@dataclass(slots=True)
class _Findings:
    """What the import has established so far; a deferral still reports it."""

    added: tuple[TrackDetail, ...] = ()
    rejected: tuple[RejectedTrack, ...] = ()
    removed: tuple[RemovedTrack, ...] = ()


# Sidecars never handed back to *arr: unwanted by the user, or gone.
_NOT_HANDED_BACK: frozenset[RejectCode] = frozenset({"language_not_kept", "file_missing"})


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
        findings = _Findings()
        try:
            return self._import(request, findings)
        except _DeferError as deferral:
            _note(deferral.stage, f"deferring to *arr: {deferral.reason}")
            return ImportOutcome(
                move_status="DeferMove",
                reason=deferral.reason,
                added_tracks=findings.added,
                rejected_tracks=findings.rejected,
                removed_tracks=findings.removed,
            )

    def _import(self, request: ImportRequest, findings: _Findings) -> ImportOutcome:
        source, destination = self._check_paths(request)
        info = self._probe_source(source)
        pruning = self._prune(info)

        accepted, rejected = self._choose(request, source, pruning)
        findings.rejected = tuple(_rejection(r) for r in rejected)
        _check_worth_muxing(info, pruning, accepted, findings.rejected)
        output = self._check_output(destination)

        findings.added = tuple(_detail(t) for t in accepted)
        findings.removed = tuple(_removal(t) for t in pruning.removed)
        if request.dry_run:
            raise _DeferError("dry run")

        self._mux(request, source, info, pruning, accepted, output)

        summary = _summary(findings.added, findings.removed)
        _note(LogStage.OUTCOME, summary, output=output)
        return ImportOutcome(
            move_status="RenameRequested",
            reason=summary,
            media_file=output,
            # Hand the unembedded subtitles back so they are not silently lost.
            extra_files=tuple(
                r.track.path
                for r in rejected
                if r.track.kind == "subtitles" and r.code not in _NOT_HANDED_BACK
            ),
            prevent_extra_import=True,
            added_tracks=findings.added,
            rejected_tracks=findings.rejected,
            removed_tracks=findings.removed,
        )

    def _check_paths(self, request: ImportRequest) -> tuple[Path, Path]:
        try:
            source = self._guard.check_read(request.source_path)
            destination = self._guard.check_destination(request.destination_path)
        except MuxarrError as exc:
            raise _DeferError(f"path rejected: {exc}", LogStage.GUARD) from exc

        _note(
            LogStage.GUARD,
            "paths accepted",
            source=source,
            destination=destination,
            mode=request.transfer_mode,
        )
        if not source.is_file():
            raise _DeferError(f"source does not exist: {source}", LogStage.GUARD)
        return source, destination

    def _probe_source(self, source: Path) -> MediaInfo:
        try:
            info = self._prober.probe(source)
        except MuxarrError as exc:
            raise _DeferError(f"could not probe source: {exc}", LogStage.PROBE) from exc

        _note(LogStage.PROBE, f"source already holds {_inventory(info)}", container=info.container)
        for existing in info.tracks:
            if existing.kind != "video":
                log.bind(
                    codec=existing.codec_family,
                    name=existing.name,
                    forced=existing.forced,
                ).debug(f"existing {existing.kind} track: {existing.language}")
        return info

    def _prune(self, info: MediaInfo) -> selection.Pruning:
        pruning = selection.prune(info, self._settings.selection_policy)
        why = selection.REJECT_REASONS["language_not_kept"]
        for stripped in pruning.removed:
            _note(
                LogStage.SELECTION,
                f"stripping source {_summarise_existing(stripped)}: {why}",
                track_id=stripped.index,
            )
        return pruning

    def _choose(
        self, request: ImportRequest, source: Path, pruning: selection.Pruning
    ) -> tuple[tuple[ExternalTrack, ...], tuple[selection.Rejection, ...]]:
        settings = self._settings
        policy = settings.selection_policy

        candidates = self._tracks.discover(source, episode=request.episode_ref)
        if not candidates and not pruning:
            raise _DeferError("no external tracks found beside the source", LogStage.DISCOVERY)

        if candidates:
            _note(
                LogStage.DISCOVERY,
                f"found {len(candidates)} sidecar file(s) worth considering",
                identified_by_ai=sum(1 for c in candidates if c.source == "ai"),
            )
        else:
            _note(LogStage.DISCOVERY, "no sidecar files found; remuxing only to strip tracks")

        _note(
            LogStage.SELECTION,
            f"comparing against the container, de-duplicating by {policy.dedupe}",
            max_tracks=policy.max_external_tracks,
            skip_image_subtitles=policy.skip_image_subtitles,
            skip_undetermined=policy.skip_undetermined_language,
            keep_audio=",".join(settings.keep_audio_languages) or "all",
            keep_subtitles=",".join(settings.keep_subtitle_languages) or "all",
        )
        present, missing = _split_missing(candidates)
        chosen = selection.select(pruning.kept, present, policy)
        accepted, unreadable = self._drop_unreadable(chosen.accepted)
        rejected = (*missing, *chosen.rejected, *unreadable)

        for track in accepted:
            _note(
                LogStage.SELECTION,
                f"embedding {_summarise(track)}, {_origin(track)}",
                file=track.path.name,
            )
        for rejection in rejected:
            _note(
                LogStage.SELECTION,
                f"skipping {_summarise(rejection.track)}: {rejection.reason}",
                file=rejection.track.path.name,
            )
        return accepted, rejected

    def _check_output(self, destination: Path) -> Path:
        output = destination.with_suffix(OUTPUT_SUFFIX)
        try:
            self._guard.check_destination(output)
        except MuxarrError as exc:
            raise _DeferError(f"output path rejected: {exc}", LogStage.GUARD) from exc
        return output

    def _mux(
        self,
        request: ImportRequest,
        source: Path,
        info: MediaInfo,
        pruning: selection.Pruning,
        tracks: Sequence[ExternalTrack],
        output: Path,
    ) -> None:
        placement = PlacementPolicy(
            scratch_dir=self._settings.scratch_dir,
            free_space_factor=self._settings.free_space_factor,
            preserve_ownership=self._settings.preserve_ownership,
        )
        try:
            self._ensure_room(source, tracks, output, placement)
            _note(
                LogStage.MUX,
                f"remuxing into {output.name}",
                tracks=len(tracks),
                stripped=len(pruning.removed),
            )
            self._mux_into_place(request, info, pruning, tracks, output, placement)
        except MuxarrError as exc:
            reason = f"mux failed, leaving the import to *arr: {exc}"
            raise _DeferError(reason, LogStage.MUX) from exc

    def _drop_unreadable(
        self, accepted: Sequence[ExternalTrack]
    ) -> tuple[tuple[ExternalTrack, ...], tuple[selection.Rejection, ...]]:
        """Split off the sidecars mkvmerge cannot get a track out of.

        One identify per file is nothing next to discovering the same thing after
        a remux that has already been running for hours.
        """
        usable: list[ExternalTrack] = []
        unreadable: list[selection.Rejection] = []

        for track in accepted:
            try:
                probed = self._prober.probe(track.path)
            except MuxarrError as exc:
                unreadable.append(selection.Rejection(track, "uninspectable", str(exc)))
                continue
            if probed.tracks:
                usable.append(track)
            else:
                unreadable.append(selection.Rejection(track, "no_tracks"))

        return tuple(usable), tuple(unreadable)

    def _ensure_room(
        self,
        source: Path,
        tracks: Sequence[ExternalTrack],
        output: Path,
        policy: PlacementPolicy,
    ) -> None:
        required = source.stat().st_size + sum(t.path.stat().st_size for t in tracks)
        self._placement.ensure_free_space(output.parent, required, factor=policy.free_space_factor)

    def _mux_into_place(
        self,
        request: ImportRequest,
        info: MediaInfo,
        pruning: selection.Pruning,
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
                keep_audio=_kept_ids(pruning, "audio"),
                keep_subtitles=_kept_ids(pruning, "subtitles"),
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


def _split_missing(
    candidates: Sequence[ExternalTrack],
) -> tuple[list[ExternalTrack], list[selection.Rejection]]:
    present: list[ExternalTrack] = []
    missing: list[selection.Rejection] = []
    for track in candidates:
        if not track.path.is_file():
            missing.append(selection.Rejection(track, "file_missing"))
        elif track.path.stat().st_size == 0:
            missing.append(selection.Rejection(track, "file_empty"))
        else:
            present.append(track)
    return present, missing


def _check_worth_muxing(
    info: MediaInfo,
    pruning: selection.Pruning,
    accepted: Sequence[ExternalTrack],
    rejections: Sequence[RejectedTrack],
) -> None:
    if not accepted and not pruning:
        reasons = "; ".join(f"{r.track}: {r.reason}" for r in rejections)
        raise _DeferError(f"nothing worth embedding ({reasons or 'no candidates'})")

    if info.audio and not pruning.kept.audio and not any(t.kind == "audio" for t in accepted):
        languages = ", ".join(sorted({t.language for t in info.audio}))
        raise _DeferError(
            f"the keep list would strip every audio track ({languages}), leaving the file silent",
            LogStage.SELECTION,
        )


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


def _summarise_existing(track: Track) -> str:
    label = track.name or track.language
    forced = " (forced)" if track.forced else ""
    return f"{track.kind} {label} [{track.language}]{forced}, track {track.index}"


def _summary(details: Sequence[TrackDetail], removals: Sequence[RemovedTrack]) -> str:
    parts = []
    if details:
        parts.append(f"embedded {len(details)} external track(s)")
    if removals:
        parts.append(f"removed {len(removals)} source track(s)")
    return ", ".join(parts)


def _kept_ids(pruning: selection.Pruning, kind: TrackKind) -> tuple[int, ...] | None:
    """The source IDs mkvmerge should copy, or None when this kind is left alone."""
    if not any(t.kind == kind for t in pruning.removed):
        return None
    return tuple(t.index for t in pruning.kept.of_kind(kind))


def _removal(track: Track) -> RemovedTrack:
    return RemovedTrack(
        index=track.index,
        kind=track.kind,
        language=track.language,
        name=track.name,
        codec=track.codec_family,
        forced=track.forced,
        reason=selection.REJECT_REASONS["language_not_kept"],
    )


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


def _rejection(rejection: selection.Rejection) -> RejectedTrack:
    track = rejection.track
    return RejectedTrack(
        track=track.path.name,
        reason=rejection.reason,
        kind=track.kind,
        language=track.language,
        source=track.source,
        code=rejection.code,
    )
