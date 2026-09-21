"""Liveness and configuration echo. Unauthenticated on purpose."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from src import __version__
from src.api.dependencies.auth import get_container
from src.core.container import AppContainer
from src.schemas.health import Health

router = APIRouter(tags=["health"])


@router.get("/healthz", response_model=Health)
async def healthz(container: Annotated[AppContainer, Depends(get_container)]) -> Health:
    # worker_status(), not execute(): a liveness probe should not pay for the
    # queue count on every poll.
    worker = await container.system_status.worker_status()
    return Health(
        version=__version__,
        read_roots=[str(r) for r in container.guard.read_roots],
        auth_required=container.settings.auth_token is not None,
        worker_seen_at=worker.last_seen_at,
        worker_alive=worker.alive,
    )
