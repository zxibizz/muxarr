"""Command line interface.

``inspect`` and ``plan`` are read-only and safe to run against a live library;
``mux`` is the only subcommand that writes anything.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from muxarr import discovery, probe, selection
from muxarr.discovery import EpisodeRef
from muxarr.errors import MuxarrError
from muxarr.models import ExternalTrack, MediaInfo, Track
from muxarr.mux import MuxPlan, run_mux
from muxarr.placement import (
    PlacementPolicy,
    copy_attributes,
    ensure_free_space,
    finalise,
    staged_output,
)

log = logging.getLogger("muxarr")


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    try:
        handler = {"inspect": _cmd_inspect, "plan": _cmd_plan, "mux": _cmd_mux}[args.command]
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
    info = probe.probe(args.video)
    print(f"{info.path}  [{info.container}]")
    for track in info.tracks:
        print(f"  {_describe_track(track)}")
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

    modern = probe.supports_modern_flag_syntax(probe.mkvmerge_version())

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
    info = probe.probe(args.video)
    candidates = discovery.discover(args.video, episode=_episode_ref(args))
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
