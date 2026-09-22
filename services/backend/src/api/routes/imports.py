"""Import submission and the shim's long-poll transport."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi import Path as PathParam
from fastapi.responses import PlainTextResponse

from src.api import protocol
from src.api.dependencies.auth import authorise, get_container
from src.application.interfaces.jobs import MAX_JOB_PAGE_SIZE
from src.core.container import AppContainer
from src.domain.enums import JobState
from src.schemas.imports import (
    JOB_ID_PATTERN,
    ImportPayload,
    JobDetailModel,
    JobModel,
    JobPageModel,
)

router = APIRouter(prefix="/v1", tags=["imports"], dependencies=[Depends(authorise)])

DEFAULT_POLL_WAIT = 25.0


@router.post("/import", response_model=JobModel, status_code=status.HTTP_202_ACCEPTED)
async def import_media(
    payload: ImportPayload,
    container: Annotated[AppContainer, Depends(get_container)],
) -> JobModel:
    """Queue an import and return immediately; the worker picks it up.

    Idempotent on ``job_id`` so the shim can retry a submission whose reply was
    lost without queueing the mux twice.
    """
    job = await container.enqueue_import.execute(
        payload.job_id, payload.fingerprint(), payload.to_request()
    )
    return JobModel.from_job(job)


@router.get("/jobs", response_model=JobPageModel)
async def list_jobs(
    container: Annotated[AppContainer, Depends(get_container)],
    state: JobState | None = None,
    limit: int = Query(20, ge=1, le=MAX_JOB_PAGE_SIZE),
    offset: int = Query(0, ge=0),
) -> JobPageModel:
    """Recent jobs, log included: the only view of one that never reached the history."""
    page = await container.list_jobs.execute(state=state, limit=limit, offset=offset)
    return JobPageModel(
        items=[JobDetailModel.from_job(job) for job in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/jobs/{job_id}", response_model=JobModel)
async def get_job(
    job_id: Annotated[str, PathParam(pattern=JOB_ID_PATTERN)],
    container: Annotated[AppContainer, Depends(get_container)],
    wait: float = Query(0.0, ge=0),
) -> JobModel:
    job = await container.await_job.execute(job_id, _clamp_wait(container, wait))
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown job")
    return JobModel.from_job(job)


@router.get("/jobs/{job_id}/detail", response_model=JobDetailModel)
async def get_job_detail(
    job_id: Annotated[str, PathParam(pattern=JOB_ID_PATTERN)],
    container: Annotated[AppContainer, Depends(get_container)],
) -> JobDetailModel:
    """The same job with its captured log, for the UI to poll while it runs."""
    job = await container.await_job.execute(job_id, 0.0)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown job")
    return JobDetailModel.from_job(job)


@router.get("/jobs/{job_id}/protocol", response_class=PlainTextResponse)
async def get_job_protocol(
    job_id: Annotated[str, PathParam(pattern=JOB_ID_PATTERN)],
    container: Annotated[AppContainer, Depends(get_container)],
    wait: float = Query(DEFAULT_POLL_WAIT, ge=0),
) -> PlainTextResponse:
    """Long-poll transport for the shim, rendered as *arr's stdout protocol.

    Always 200, with the state in the body: curl and busybox wget surface non-2xx
    so differently that a sh shim cannot tell "unknown job" from "connection
    refused". Encoding state in the body makes a missing state line mean exactly
    one thing -- transport failure, worth retrying.
    """
    job = await container.await_job.execute(job_id, _clamp_wait(container, wait))
    if job is None:
        body = protocol.render_poll(protocol.STATE_UNKNOWN)
    elif job.state == "succeeded" and job.outcome is not None:
        body = protocol.render_poll(protocol.STATE_DONE, job.outcome)
    elif job.state == "failed":
        body = protocol.render_poll(protocol.STATE_ERROR)
    else:
        body = protocol.render_poll(protocol.STATE_RUNNING)
    return PlainTextResponse(body)


def _clamp_wait(container: AppContainer, wait: float) -> float:
    return min(wait, container.settings.max_poll_wait_seconds)
