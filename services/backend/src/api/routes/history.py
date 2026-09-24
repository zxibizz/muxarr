"""Operation history and aggregate stats."""

from __future__ import annotations

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from src.api.dependencies.auth import authorise, get_container
from src.application.interfaces.history import MAX_PAGE_SIZE
from src.core.container import AppContainer
from src.schemas.history import ClearedModel, HistoryPage, OperationModel, StatsModel

router = APIRouter(prefix="/v1", tags=["history"], dependencies=[Depends(authorise)])


@router.get("/history", response_model=HistoryPage)
async def list_history(
    container: Annotated[AppContainer, Depends(get_container)],
    limit: int = Query(50, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0),
    move_status: str | None = None,
    app_name: str | None = Query(None, alias="app"),
    q: str | None = None,
) -> HistoryPage:
    page = await container.list_operations.execute(
        limit=limit, offset=offset, status=move_status, app=app_name, query=q
    )
    return HistoryPage(
        items=[OperationModel.from_record(op) for op in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/history/{operation_id}", response_model=OperationModel)
async def get_operation(
    operation_id: int,
    container: Annotated[AppContainer, Depends(get_container)],
) -> OperationModel:
    found = await container.get_operation.execute(operation_id)
    return OperationModel.from_record(found)


@router.delete("/history", response_model=ClearedModel)
async def clear_history(
    container: Annotated[AppContainer, Depends(get_container)],
) -> ClearedModel:
    return ClearedModel(deleted=await container.clear_history.execute())


@router.get("/stats", response_model=StatsModel)
async def get_stats(container: Annotated[AppContainer, Depends(get_container)]) -> StatsModel:
    return StatsModel(**asdict(await container.get_stats.execute()))
