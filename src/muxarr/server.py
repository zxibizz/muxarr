"""HTTP daemon.

Runs in its own container alongside Radarr/Sonarr, owning the ffmpeg/mkvtoolnix
dependency so the *arr container needs nothing but a shell.

Keeping the mux out-of-process also means stray mkvmerge output can never reach
the shim's stdout, where *arr would try to parse it as protocol.
"""

from __future__ import annotations

import asyncio
import hmac
import logging
from functools import partial
from pathlib import Path
from typing import Annotated, Literal

import anyio.to_thread
from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from muxarr import __version__
from muxarr.config import Settings
from muxarr.paths import PathGuard
from muxarr.pipeline import ImportOutcome, ImportRequest, handle_import
from muxarr.protocol import render_text

log = logging.getLogger(__name__)


class ImportPayload(BaseModel):
    app: Literal["radarr", "sonarr"]
    source_path: str
    destination_path: str
    library_path: str
    transfer_mode: str = "Move"
    season: int | None = None
    episodes: list[int] = Field(default_factory=list)
    dry_run: bool = False

    def to_request(self) -> ImportRequest:
        return ImportRequest(
            app=self.app,
            source_path=Path(self.source_path),
            destination_path=Path(self.destination_path),
            library_path=Path(self.library_path),
            transfer_mode=self.transfer_mode,
            season=self.season,
            episodes=tuple(self.episodes),
            dry_run=self.dry_run,
        )


class ImportResult(BaseModel):
    move_status: str
    reason: str
    media_file: str | None = None
    extra_files: list[str] = Field(default_factory=list)
    prevent_extra_import: bool = False
    added_tracks: list[str] = Field(default_factory=list)

    @classmethod
    def from_outcome(cls, outcome: ImportOutcome) -> ImportResult:
        return cls(
            move_status=outcome.move_status,
            reason=outcome.reason,
            media_file=str(outcome.media_file) if outcome.media_file else None,
            extra_files=[str(p) for p in outcome.extra_files],
            prevent_extra_import=outcome.prevent_extra_import,
            added_tracks=list(outcome.added_tracks),
        )


class Health(BaseModel):
    status: Literal["ok"] = "ok"
    version: str
    read_roots: list[str]


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(title="muxarr", version=__version__)
    guard = PathGuard.from_roots(settings.read_roots)
    semaphore = asyncio.Semaphore(settings.max_concurrent_muxes)

    def authorise(authorization: Annotated[str | None, Header()] = None) -> None:
        if settings.auth_token is None:
            return
        supplied = ""
        if authorization and authorization.lower().startswith("bearer "):
            supplied = authorization[7:].strip()
        # Constant-time: a plain == leaks the token prefix through timing.
        if not hmac.compare_digest(supplied, settings.auth_token):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid or missing token"
            )

    @app.get("/healthz", response_model=Health)
    def healthz() -> Health:
        return Health(version=__version__, read_roots=[str(r) for r in guard.read_roots])

    @app.post(
        "/v1/import",
        response_model=ImportResult,
        dependencies=[Depends(authorise)],
    )
    async def import_media(payload: ImportPayload) -> ImportResult:
        return ImportResult.from_outcome(await _run(payload))

    @app.post(
        "/v1/import/protocol",
        response_class=PlainTextResponse,
        dependencies=[Depends(authorise)],
    )
    async def import_media_protocol(payload: ImportPayload) -> PlainTextResponse:
        """Same work, rendered as *arr's stdout protocol.

        Lets the shim be a dumb pipe instead of a JSON parser written in sh.
        """
        return PlainTextResponse(render_text(await _run(payload)))

    async def _run(payload: ImportPayload) -> ImportOutcome:
        request = payload.to_request()
        log.info(
            "import request app=%s mode=%s source=%s",
            request.app,
            request.transfer_mode,
            request.source_path,
        )
        # One mux at a time by default; concurrent remuxes on one spindle are
        # slower than running them back to back.
        async with semaphore:
            outcome = await anyio.to_thread.run_sync(
                partial(handle_import, request, settings, guard)
            )
        log.info("import result status=%s reason=%s", outcome.move_status, outcome.reason)
        return outcome

    return app


def serve(settings: Settings | None = None) -> None:
    import uvicorn

    resolved = settings or Settings.from_env()
    logging.basicConfig(
        level=resolved.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if resolved.auth_token is None:
        log.warning(
            "MUXARR_TOKEN is not set; the API is unauthenticated. "
            "Bind to a private network only."
        )
    uvicorn.run(create_app(resolved), host=resolved.host, port=resolved.port)
