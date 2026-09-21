"""Liveness and configuration echo. Unauthenticated on purpose."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends

from src import __version__
from src.api.dependencies.auth import get_container
from src.core.container import AppContainer
from src.schemas.health import Health
from src.worker.service import HEARTBEAT_INTERVAL

router = APIRouter(tags=["health"])

# Generous next to HEARTBEAT_INTERVAL: a worker busy with a mux still beats
# between polls, and a brief stall is not worth reporting as dead.
WORKER_STALE_AFTER = HEARTBEAT_INTERVAL * 6


@router.get("/healthz", response_model=Health)
async def healthz(container: Annotated[AppContainer, Depends(get_container)]) -> Health:
    last_seen = await container.worker_state.last_seen()
    return Health(
        version=__version__,
        read_roots=[str(r) for r in container.guard.read_roots],
        auth_required=container.settings.auth_token is not None,
        worker_seen_at=last_seen,
        worker_alive=_is_fresh(last_seen),
    )


def _is_fresh(last_seen: str | None) -> bool:
    if last_seen is None:
        return False
    try:
        seen = datetime.fromisoformat(last_seen.replace("Z", "+00:00"))
    except ValueError:
        return False
    return (datetime.now(UTC) - seen).total_seconds() <= WORKER_STALE_AFTER
