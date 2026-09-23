"""Command line interface.

``inspect`` and ``plan`` are read-only and safe to run against a live library;
``mux`` is the only subcommand that writes anything.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
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
            "openapi": _cmd_openapi,
            "wait-for-schema": _cmd_wait_for_schema,
            "worker-alive": _cmd_worker_alive,
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

    openapi = sub.add_parser("openapi", help="print the HTTP API's OpenAPI schema as JSON")
    openapi.add_argument("--out", type=Path, default=None, help="write here instead of stdout")

    wait = sub.add_parser(
        "wait-for-schema",
        help="block until MUXARR_DB_URL is reachable and migrated to this build's head",
    )
    wait.add_argument("--timeout", type=float, default=120.0, help="seconds; exit 1 after")
    wait.add_argument("--interval", type=float, default=2.0, help="seconds between checks")

    sub.add_parser("worker-alive", help="exit 0 if the worker's heartbeat is fresh, else 1")

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


def _cmd_openapi(args: argparse.Namespace) -> int:
    from src.api.app import create_app
    from src.settings.config import Settings

    # The schema does not depend on configuration; nothing here touches the roots.
    schema = create_app(Settings(read_roots=(Path("/"),))).openapi()
    text = json.dumps(schema, indent=2, sort_keys=True) + "\n"
    if args.out is None:
        sys.stdout.write(text)
    else:
        args.out.write_text(text, encoding="utf-8")
    return 0


def _cmd_wait_for_schema(args: argparse.Namespace) -> int:
    return asyncio.run(_wait_for_schema(args.timeout, args.interval))


async def _wait_for_schema(timeout: float, interval: float) -> int:
    from src.db.migrations import schema_is_current
    from src.db.session import DBManager
    from src.settings.config import normalise_db_url

    # Only the URL: waiting on the database should not need the rest configured.
    db = DBManager(normalise_db_url(os.environ.get("MUXARR_DB_URL", "")))
    deadline = time.monotonic() + timeout
    announced = False
    try:
        while True:
            try:
                if await schema_is_current(db.engine):
                    return 0
                reason = "the schema does not match this build's migrations"
            except Exception as exc:  # the database may simply not be up yet
                reason = f"{type(exc).__name__}: {exc}"
            if time.monotonic() >= deadline:
                print(f"error: schema not ready after {timeout:g}s: {reason}", file=sys.stderr)
                return 1
            if not announced:
                print(f"waiting up to {timeout:g}s for the database schema: {reason}")
                announced = True
            await asyncio.sleep(interval)
    finally:
        await db.dispose()


def _cmd_worker_alive(_args: argparse.Namespace) -> int:
    return asyncio.run(_worker_alive())


async def _worker_alive() -> int:
    from src.core.container import AppContainer
    from src.settings.config import Settings

    container = AppContainer(Settings.from_env())
    try:
        status = await container.system_status.worker_status()
    finally:
        await container.shutdown()
    if status.alive:
        return 0
    seen = status.last_seen_at or "never"
    print(f"worker heartbeat is stale (last seen: {seen})", file=sys.stderr)
    return 1


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
    for rejection in chosen.rejected:
        print(f"  - skip    {_describe_external(rejection.track)}  ({rejection.reason})")


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
