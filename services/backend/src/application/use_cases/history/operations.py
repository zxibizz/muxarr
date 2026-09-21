"""Read and mutate the operation log."""

from __future__ import annotations

from src.application.interfaces.history import HistoryRepository, OperationRecord, Page, Stats
from src.application.use_cases.history.exceptions import OperationNotFoundError


class ListOperationsUseCase:
    def __init__(self, repository: HistoryRepository) -> None:
        self._repository = repository

    async def execute(
        self,
        *,
        limit: int,
        offset: int,
        status: str | None = None,
        app: str | None = None,
        query: str | None = None,
    ) -> Page:
        return await self._repository.list(
            limit=limit, offset=offset, status=status, app=app, query=query
        )


class GetOperationUseCase:
    def __init__(self, repository: HistoryRepository) -> None:
        self._repository = repository

    async def execute(self, operation_id: int) -> OperationRecord:
        record = await self._repository.get(operation_id)
        if record is None:
            raise OperationNotFoundError(operation_id)
        return record


class GetStatsUseCase:
    def __init__(self, repository: HistoryRepository) -> None:
        self._repository = repository

    async def execute(self) -> Stats:
        return await self._repository.stats()


class ClearHistoryUseCase:
    def __init__(self, repository: HistoryRepository) -> None:
        self._repository = repository

    async def execute(self) -> int:
        return await self._repository.clear()
