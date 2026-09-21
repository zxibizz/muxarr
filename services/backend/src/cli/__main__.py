"""Command line interface.

``inspect`` and ``plan`` are read-only and safe to run against a live library;
``mux`` is the only subcommand that writes anything.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.application.interfaces.muxer import MuxPlan
from src.application.interfaces.placement import PlacementPolicy
from src.core.logging import configure_logging
from src.domain import selection
from src.domain.errors import MuxarrError
from src.domain.media import ExternalTrack, MediaInfo, Track
from src.domain.naming import EpisodeRef
from src.infrastructure.filesystem.placement import (
    copy_attributes,
    ensure_free_space,
    finalise,
    staged_output,
)
from src.infrastructure.filesystem.track_discovery import discover
from src.infrastructure.mkvtoolnix.muxer import run_mux
from src.infrastructure.mkvtoolnix.probe import mkvmerge_version, supports_modern_flag_syntax
from src.infrastructure.probing import probe


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    configure_logging(level="DEBUG" if args.verbose else "INFO")

    try:
        handler = {
            "inspect": _cmd_inspect,
            "plan": _cmd_plan,
            "mux": _cmd_mux,
            "serve": _cmd_serve,
        }[args.command]
        return handler(args)
    except MuxarrError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="muxarr", description=__doc__)
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    inspect = sub.add_parser("inspect", help="list the tracks inside a container")
    inspect.add_argument("video", type=Path)

    plan = sub.add_parser("plan", help="show what would be embedded, without writing")
    _add_discovery_args(plan)

    mux = sub.add_parser("mux", help="embed discovered sidecars into a new MKV")
    _add_discovery_args(mux)
    mux.add_argument("--out", type=Path, required=True, help="destination .mkv path")
    mux.add_argument(
        "--scratch-dir",
        type=Path,
        default=None,
        help="stage here instead of the destination directory (rarely a good idea)",
    )

    sub.add_parser("serve", help="run the HTTP daemon (configured via MUXARR_* env vars)")

    return parser


def _add_discovery_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("video", type=Path)
    parser.add_argument("--season", type=int, default=None)
    parser.add_argument(
        "--episodes",
        default="",
        help="comma separated episode numbers, for season-pack sidecar matching",
    )


def _episode_ref(args: argparse.Namespace) -> EpisodeRef | None:
    if args.season is None:
        return None
    numbers = tuple(int(n) for n in str(args.episodes).split(",") if n.strip())
    return EpisodeRef(season=args.season, episodes=numbers)


def _cmd_inspect(args: argparse.Namespace) -> int:
    info = probe(args.video)
    print(f"{info.path}  [{info.container}]")
    for track in info.tracks:
        print(f"  {_describe_track(track)}")
    return 0


def _cmd_serve(_args: argparse.Namespace) -> int:
    from src.api.app import serve

    serve()
    return 0


def _cmd_plan(args: argparse.Namespace) -> int:
    info, chosen = _prepare(args)
    _report(info, chosen)
    return 0


def _cmd_mux(args: argparse.Namespace) -> int:
    info, chosen = _prepare(args)
    _report(info, chosen)

    if not chosen:
        print("nothing to embed; no output written")
        return 0

    destination: Path = args.out
    policy = PlacementPolicy(scratch_dir=args.scratch_dir)
    required = args.video.stat().st_size + sum(t.path.stat().st_size for t in chosen.accepted)
    ensure_free_space(destination.parent, required, factor=policy.free_space_factor)

    modern = supports_modern_flag_syntax(mkvmerge_version())

    with staged_output(destination, policy) as staging:
        plan = MuxPlan(
            source=args.video,
            output=staging,
            tracks=chosen.accepted,
            modern_flags=modern,
        )
        run_mux(plan, info)
        finalise(staging, destination, policy)

    copy_attributes(args.video, destination, policy)
    print(f"wrote {destination}")
    return 0


def _prepare(args: argparse.Namespace) -> tuple[MediaInfo, selection.Selection]:
    info = probe(args.video)
    candidates = discover(args.video, episode=_episode_ref(args))
    return info, selection.select(info, candidates)


def _report(info: MediaInfo, chosen: selection.Selection) -> None:
    print(f"{info.path}  [{info.container}]")
    for existing in info.tracks:
        print(f"  existing  {_describe_track(existing)}")
    for added in chosen.accepted:
        print(f"  + add     {_describe_external(added)}")
    for skipped, reason in chosen.rejected:
        print(f"  - skip    {_describe_external(skipped)}  ({reason})")


def _describe_track(track: Track | ExternalTrack) -> str:
    return f"{track.kind:<9} {track.language:<4} {track.codec_family:<8}{_flags(track)}"


def _describe_external(track: ExternalTrack) -> str:
    return f"{_describe_track(track)}  {track.path.name}"


def _flags(track: Track | ExternalTrack) -> str:
    names: list[str] = []
    if getattr(track, "default", False):
        names.append("default")
    if track.forced:
        names.append("forced")
    if track.hearing_impaired:
        names.append("sdh")
    return f" [{', '.join(names)}]" if names else ""


if __name__ == "__main__":
    raise SystemExit(main())
