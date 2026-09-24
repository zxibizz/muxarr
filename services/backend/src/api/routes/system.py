"""Worker liveness and job queue depth.

Behind auth, unlike /healthz: the queue counts describe what the daemon is
doing, which is more than an unauthenticated liveness probe should say.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends

from src import __version__
from src.api.dependencies.auth import authorise, get_container
from src.core.container import AppContainer
from src.schemas.system import (
    HealthIssueModel,
    QueueStatusModel,
    SystemStatus,
    WorkerStatusModel,
)

router = APIRouter(prefix="/v1", tags=["system"], dependencies=[Depends(authorise)])


@router.get("/system", response_model=SystemStatus)
async def get_system(
    container: Annotated[AppContainer, Depends(get_container)],
) -> SystemStatus:
    status = await container.system_status.execute()
    return SystemStatus(
        version=__version__,
        worker=WorkerStatusModel(**asdict(status.worker)),
        queue=QueueStatusModel(**asdict(status.queue)),
        health=[HealthIssueModel(**asdict(issue)) for issue in status.health],
    )
