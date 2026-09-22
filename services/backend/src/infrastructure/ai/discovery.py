"""Optional LLM-assisted sidecar discovery.

Wraps the filename heuristic rather than replacing it. The heuristic runs on every
import regardless of mode -- it is a directory listing, and it is what the AI path
degrades to when the provider is slow, broken, or talking nonsense.

Everything the model returns is untrusted input. It is never used as a path: a
proposal is matched against the candidate index built from the real directory
listing, so the model can only select and label files that already exist. The
track's ``kind`` comes from its extension, not from the model, and an
unrecognised language becomes ``und`` rather than a guess.

Nothing here raises. ``HandleImportUseCase.execute`` must not fail an import
because an API call did.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from src.application.interfaces.ai import ChatCompleter
from src.application.interfaces.track_source import TrackDiscovery
from src.core.logging import get_logger
from src.domain.enums import UNDETERMINED, AiMode, LogComponent
from src.domain.language import normalise_language
from src.domain.media import ExternalTrack
from src.domain.naming import EpisodeRef
from src.infrastructure.ai import prompt as prompt_builder
from src.infrastructure.filesystem.track_discovery import classify

log = get_logger(LogComponent.INFRA_AI)

# Track names and dub tags end up in the Matroska header and in an mkvmerge argv.
MAX_LABEL_CHARS = 120

_FENCE = re.compile(r"^```(?:json)?|```$", re.MULTILINE)
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


class AiAssistedTrackDiscovery:
    """Adapter object for the container; implements ``TrackDiscovery``."""

    def __init__(
        self,
        *,
        heuristic: TrackDiscovery,
        completer: ChatCompleter,
        mode: AiMode,
        max_entries: int = 200,
        timeout: float = 30.0,
        max_tracks: int = 24,
    ) -> None:
        self._heuristic = heuristic
        self._completer = completer
        self._mode = mode
        self._max_entries = max_entries
        self._timeout = timeout
        self._max_tracks = max_tracks

    def discover(
        self, video_path: Path, *, episode: EpisodeRef | None = None
    ) -> list[ExternalTrack]:
        found = self._heuristic.discover(video_path, episode=episode)
        if not self._should_consult(found):
            return found

        proposed = self._consult(video_path, episode=episode)
        if proposed is None:
            return found

        if self._mode == "verify":
            _log_disagreement(found, proposed)
            return found

        log.info(
            "ai discovery accepted",
            video=video_path.name,
            heuristic_tracks=len(found),
            ai_tracks=len(proposed),
        )
        return proposed

    def _should_consult(self, found: Sequence[ExternalTrack]) -> bool:
        if self._mode == "off":
            return False
        if self._mode in ("always", "verify"):
            return True
        # fallback: only when the filenames did not settle it on their own.
        return not found or any(track.language == UNDETERMINED for track in found)

    def _consult(
        self, video_path: Path, *, episode: EpisodeRef | None
    ) -> list[ExternalTrack] | None:
        built = prompt_builder.build(video_path, episode=episode, max_entries=self._max_entries)
        if built is None:
            return None

        try:
            reply = self._completer.complete(
                system=built.system, user=built.user, timeout=self._timeout
            )
        except Exception as exc:  # noqa: BLE001 - a bad API call must never fail an import
            log.warning(
                "ai discovery unavailable, keeping the filename heuristic",
                video=video_path.name,
                error=str(exc),
            )
            return None

        tracks = materialise(reply, index=built.index, max_tracks=self._max_tracks)
        return tracks or None


def materialise(
    reply: str, *, index: Mapping[str, Path], max_tracks: int
) -> list[ExternalTrack]:
    """Validate a model reply into tracks, dropping anything that does not check out."""
    tracks: list[ExternalTrack] = []
    seen: set[Path] = set()

    for item in _parse(reply):
        track = _to_track(item, index=index)
        if track is None or track.path in seen:
            continue
        seen.add(track.path)
        tracks.append(track)
        if len(tracks) >= max_tracks:
            log.warning("ai proposed more tracks than allowed, truncating", limit=max_tracks)
            break

    return tracks


def _parse(reply: str) -> list[Any]:
    # Models fence their JSON even when told not to.
    text = _FENCE.sub("", reply.strip()).strip()
    try:
        data = json.loads(text)
    except ValueError:
        log.warning("ai reply was not valid JSON", preview=text[:200])
        return []

    if isinstance(data, dict):
        data = data.get("tracks")
    if not isinstance(data, list):
        log.warning("ai reply carried no track list")
        return []
    return data


def _to_track(item: Any, *, index: Mapping[str, Path]) -> ExternalTrack | None:
    if not isinstance(item, dict):
        return None

    raw_file = item.get("file")
    if not isinstance(raw_file, str):
        return None

    # The lookup is the whole path guard: "..", absolute paths, symlink escapes and
    # outright hallucinations all fail to be keys.
    path = index.get(raw_file.strip().replace("\\", "/"))
    if path is None:
        log.warning("ai proposed a file that is not a candidate", file=raw_file[:MAX_LABEL_CHARS])
        return None

    classified = classify(path)
    if classified is None:
        return None
    kind, companion = classified

    return ExternalTrack(
        path=path,
        kind=kind,
        language=_language(item.get("language")),
        name=_label(item.get("title")),
        forced=item.get("forced") is True,
        hearing_impaired=item.get("hearing_impaired") is True,
        variant=_label(item.get("variant")),
        companion=companion,
        source="ai",
    )


def _language(raw: Any) -> str:
    if not isinstance(raw, str):
        return UNDETERMINED
    return normalise_language(raw) or UNDETERMINED


def _label(raw: Any) -> str | None:
    if not isinstance(raw, str):
        return None
    return " ".join(_CONTROL.sub(" ", raw).split())[:MAX_LABEL_CHARS] or None


def _log_disagreement(found: Sequence[ExternalTrack], proposed: Sequence[ExternalTrack]) -> None:
    heuristic = {_fingerprint(t) for t in found}
    ai = {_fingerprint(t) for t in proposed}
    if heuristic == ai:
        log.info("ai discovery agrees with the filename heuristic", tracks=len(found))
        return

    log.warning(
        "ai discovery disagrees with the filename heuristic",
        only_heuristic=sorted(heuristic - ai),
        only_ai=sorted(ai - heuristic),
    )


def _fingerprint(track: ExternalTrack) -> str:
    flags = "".join(c for c, on in (("f", track.forced), ("h", track.hearing_impaired)) if on)
    return f"{track.path.name}|{track.kind}|{track.language}|{flags}"
