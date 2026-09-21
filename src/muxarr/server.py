"""HTTP daemon.

Runs in its own container alongside Radarr/Sonarr, owning the ffmpeg/mkvtoolnix
dependency so the *arr container needs nothing but a shell.

Keeping the mux out-of-process also means stray mkvmerge output can never reach
the shim's stdout, where *arr would try to parse it as protocol.

Imports are asynchronous: the shim submits a job and long-polls for the outcome.
Holding one request open for the length of a remux did not survive proxy idle
timeouts, and a dropped reply was indistinguishable from a failed mux.
"""

from __future__ import annotations

import asyncio
import hmac
import logging
from dataclasses import asdict
from functools import partial
from pathlib import Path
from typing import Annotated, Literal

import anyio.to_thread
from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from fastapi import Path as PathParam
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from muxarr import __version__, history, protocol
from muxarr.config import Settings
from muxarr.history import HistoryStore
from muxarr.jobs import Job, JobConflictError, JobStore, fingerprint
from muxarr.paths import PathGuard
from muxarr.pipeline import ImportOutcome, ImportRequest, handle_import

log = logging.getLogger(__name__)

# Constrained so a job id cannot smuggle path separators into the URL or control
# characters into the log.
JOB_ID_PATTERN = r"^[A-Za-z0-9._:-]{8,128}$"

DEFAULT_POLL_WAIT = 25.0


class ImportPayload(BaseModel):
    job_id: str = Field(pattern=JOB_ID_PATTERN)
    app: Literal["radarr", "sonarr"]
    source_path: str
    destination_path: str
    transfer_mode: str = "Move"
    dry_run: bool = False

    def to_request(self) -> ImportRequest:
        return ImportRequest(
            app=self.app,
            source_path=Path(self.source_path),
            destination_path=Path(self.destination_path),
            transfer_mode=self.transfer_mode,
            dry_run=self.dry_run,
        )

    def fingerprint(self) -> str:
        return fingerprint(self.model_dump(exclude={"job_id"}))


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


class JobModel(BaseModel):
    id: str
    state: str
    result: ImportResult | None = None
    error: str | None = None
    history_id: int | None = None

    @classmethod
    def from_job(cls, job: Job) -> JobModel:
        return cls(
            id=job.id,
            state=job.state,
            result=ImportResult.from_outcome(job.outcome) if job.outcome else None,
            error=job.error,
            history_id=job.history_id,
        )


class Health(BaseModel):
    status: Literal["ok"] = "ok"
    version: str
    read_roots: list[str]
    auth_required: bool = False


class OperationModel(BaseModel):
    id: int
    created_at: str
    app: str
    title: str
    move_status: str
    reason: str
    source_path: str
    destination_path: str
    media_file: str | None = None
    transfer_mode: str = ""
    season: int | None = None
    episodes: list[int] = Field(default_factory=list)
    added_tracks: list[str] = Field(default_factory=list)
    rejected_tracks: list[dict[str, str]] = Field(default_factory=list)
    duration_ms: int = 0
    source_bytes: int | None = None
    output_bytes: int | None = None
    dry_run: bool = False


class HistoryPage(BaseModel):
    items: list[OperationModel]
    total: int
    limit: int
    offset: int


class StatsModel(BaseModel):
    total: int
    muxed: int
    deferred: int
    tracks_added: int
    last_24h: int


def _title_for(request: ImportRequest) -> str:
    return Path(request.source_path).name


def create_app(
    settings: Settings,
    store: HistoryStore | None = None,
    jobs: JobStore | None = None,
) -> FastAPI:
    app = FastAPI(title="muxarr", version=__version__)
    guard = PathGuard.from_roots(settings.read_roots)
    semaphore = asyncio.Semaphore(settings.max_concurrent_muxes)
    history_store = store or history.HistoryStore()
    job_store = jobs or JobStore(ttl_seconds=settings.job_ttl_seconds)

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
        return Health(
            version=__version__,
            read_roots=[str(r) for r in guard.read_roots],
            auth_required=settings.auth_token is not None,
        )

    @app.get(
        "/v1/history",
        response_model=HistoryPage,
        dependencies=[Depends(authorise)],
    )
    def list_history(
        limit: int = Query(50, ge=1, le=history.MAX_PAGE_SIZE),
        offset: int = Query(0, ge=0),
        move_status: str | None = None,
        app_name: str | None = Query(None, alias="app"),
        q: str | None = None,
    ) -> HistoryPage:
        page = history_store.list(
            limit=limit, offset=offset, status=move_status, app=app_name, query=q
        )
        return HistoryPage(
            items=[OperationModel(**asdict(op)) for op in page.items],
            total=page.total,
            limit=page.limit,
            offset=page.offset,
        )

    @app.get(
        "/v1/history/{operation_id}",
        response_model=OperationModel,
        dependencies=[Depends(authorise)],
    )
    def get_operation(operation_id: int) -> OperationModel:
        found = history_store.get(operation_id)
        if found is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
        return OperationModel(**asdict(found))

    @app.delete("/v1/history", dependencies=[Depends(authorise)])
    def clear_history() -> dict[str, int]:
        return {"deleted": history_store.clear()}

    @app.get("/v1/stats", response_model=StatsModel, dependencies=[Depends(authorise)])
    def get_stats() -> StatsModel:
        return StatsModel(**asdict(history_store.stats()))

    @app.post(
        "/v1/import",
        response_model=JobModel,
        status_code=status.HTTP_202_ACCEPTED,
        dependencies=[Depends(authorise)],
    )
    async def import_media(payload: ImportPayload) -> JobModel:
        """Queue an import and return immediately; the shim polls for the result.

        Idempotent on ``job_id`` so the shim can retry a submission whose reply
        was lost without starting the mux twice.
        """
        try:
            job, created = job_store.create_or_get(payload.job_id, payload.fingerprint())
        except JobConflictError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        if created:
            job.task = asyncio.create_task(_run_job(job, payload))
        return JobModel.from_job(job)

    @app.get(
        "/v1/jobs/{job_id}",
        response_model=JobModel,
        dependencies=[Depends(authorise)],
    )
    async def get_job(
        job_id: Annotated[str, PathParam(pattern=JOB_ID_PATTERN)],
        wait: float = Query(0.0, ge=0),
    ) -> JobModel:
        job = await job_store.wait(job_id, _clamp_wait(wait))
        if job is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown job")
        return JobModel.from_job(job)

    @app.get(
        "/v1/jobs/{job_id}/protocol",
        response_class=PlainTextResponse,
        dependencies=[Depends(authorise)],
    )
    async def get_job_protocol(
        job_id: Annotated[str, PathParam(pattern=JOB_ID_PATTERN)],
        wait: float = Query(DEFAULT_POLL_WAIT, ge=0),
    ) -> PlainTextResponse:
        """Long-poll transport for the shim, rendered as *arr's stdout protocol.

        Always 200, with the state in the body: curl and busybox wget surface
        non-2xx so differently that a sh shim cannot tell "unknown job" from
        "connection refused". Encoding state in the body makes a missing state
        line mean exactly one thing -- transport failure, worth retrying.
        """
        job = await job_store.wait(job_id, _clamp_wait(wait))
        if job is None:
            body = protocol.render_poll(protocol.STATE_UNKNOWN)
        elif job.state == "succeeded" and job.outcome is not None:
            body = protocol.render_poll(protocol.STATE_DONE, job.outcome)
        elif job.state == "failed":
            body = protocol.render_poll(protocol.STATE_ERROR)
        else:
            body = protocol.render_poll(protocol.STATE_RUNNING)
        return PlainTextResponse(body)

    def _clamp_wait(wait: float) -> float:
        return min(wait, settings.max_poll_wait_seconds)

    async def _run_job(job: Job, payload: ImportPayload) -> None:
        request = payload.to_request()
        log.info(
            "import job=%s app=%s mode=%s source=%s",
            job.id,
            request.app,
            request.transfer_mode,
            request.source_path,
        )
        try:
            job_store.start(job.id)
            # One mux at a time by default; concurrent remuxes on one spindle are
            # slower than running them back to back.
            async with semaphore:
                outcome = await anyio.to_thread.run_sync(
                    partial(handle_import, request, settings, guard)
                )
        except Exception as exc:
            # handle_import degrades to DeferMove internally, so reaching here
            # means the daemon itself broke; the shim turns it into a failed
            # import rather than letting *arr move a possibly half-muxed file.
            log.exception("import job %s failed", job.id)
            job_store.fail(job.id, f"{type(exc).__name__}: {exc}")
            return
        log.info("import result status=%s reason=%s", outcome.move_status, outcome.reason)
        job_store.succeed(job.id, outcome, _record(request, outcome))

    def _record(request: ImportRequest, outcome: ImportOutcome) -> int | None:
        episode = request.episode_ref
        try:
            return history_store.record(
                app=request.app,
                title=_title_for(request),
                move_status=outcome.move_status,
                reason=outcome.reason,
                source_path=str(request.source_path),
                destination_path=str(request.destination_path),
                media_file=str(outcome.media_file) if outcome.media_file else None,
                transfer_mode=request.transfer_mode,
                season=episode.season if episode else None,
                episodes=episode.episodes if episode else (),
                added_tracks=outcome.added_tracks,
                rejected_tracks=outcome.rejected_tracks,
                duration_ms=outcome.duration_ms,
                source_bytes=outcome.source_bytes,
                output_bytes=outcome.output_bytes,
                dry_run=request.dry_run,
            )
        except Exception:
            # Losing a history row must never turn a good import into a failure.
            log.exception("could not record history for %s", request.source_path)
            return None

    _mount_web_ui(app, settings)
    return app


def _mount_web_ui(app: FastAPI, settings: Settings) -> None:
    """Serve the built SPA, if present.

    Mounted last on purpose: mounts are matched in registration order, so a mount
    at "/" added earlier would shadow every API route.
    """
    web_dir = settings.web_dir or Path("/app/web")
    if not (web_dir / "index.html").is_file():
        log.info("no web UI at %s; serving API only", web_dir)
        return
    app.mount("/", StaticFiles(directory=str(web_dir), html=True), name="web")
    log.info("serving web UI from %s", web_dir)


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
