"""Composition root.

Everything the API needs is built here, once, and handed out through
``Depends``. Nothing below the api layer reaches for a global.
"""

from __future__ import annotations

from functools import cached_property

from src.application.interfaces.history import HistoryRepository
from src.application.interfaces.jobs import JobStore
from src.application.use_cases.history.operations import (
    ClearHistoryUseCase,
    GetOperationUseCase,
    GetStatsUseCase,
    ListOperationsUseCase,
)
from src.application.use_cases.imports.handle_import import HandleImportUseCase
from src.application.use_cases.imports.run_job import ImportJobService
from src.db.session import DBManager
from src.domain.paths import PathGuard
from src.infrastructure.filesystem.placement import FilesystemPlacement
from src.infrastructure.filesystem.track_discovery import FilesystemTrackDiscovery
from src.infrastructure.history.repository import SqlAlchemyHistoryRepository
from src.infrastructure.jobs.memory_store import InMemoryJobStore
from src.infrastructure.mkvtoolnix.muxer import MkvmergeMuxer
from src.infrastructure.probing import FallbackMediaProber
from src.settings.config import Settings


class AppContainer:
    def __init__(
        self,
        settings: Settings,
        *,
        history: HistoryRepository | None = None,
        jobs: JobStore | None = None,
    ) -> None:
        self.settings = settings
        self._history_override = history
        self._jobs_override = jobs

    @cached_property
    def db(self) -> DBManager:
        return DBManager(self.settings.db_url)

    @cached_property
    def guard(self) -> PathGuard:
        return PathGuard.from_roots(self.settings.read_roots)

    @cached_property
    def history(self) -> HistoryRepository:
        return self._history_override or SqlAlchemyHistoryRepository(self.db)

    @cached_property
    def jobs(self) -> JobStore:
        return self._jobs_override or InMemoryJobStore(ttl_seconds=self.settings.job_ttl_seconds)

    @cached_property
    def handle_import(self) -> HandleImportUseCase:
        return HandleImportUseCase(
            settings=self.settings,
            guard=self.guard,
            prober=FallbackMediaProber(),
            tracks=FilesystemTrackDiscovery(),
            muxer=MkvmergeMuxer(),
            placement=FilesystemPlacement(),
        )

    @cached_property
    def import_jobs(self) -> ImportJobService:
        return ImportJobService(
            jobs=self.jobs,
            history=self.history,
            handler=self.handle_import,
            max_concurrent_muxes=self.settings.max_concurrent_muxes,
        )

    @cached_property
    def list_operations(self) -> ListOperationsUseCase:
        return ListOperationsUseCase(self.history)

    @cached_property
    def get_operation(self) -> GetOperationUseCase:
        return GetOperationUseCase(self.history)

    @cached_property
    def get_stats(self) -> GetStatsUseCase:
        return GetStatsUseCase(self.history)

    @cached_property
    def clear_history(self) -> ClearHistoryUseCase:
        return ClearHistoryUseCase(self.history)

    async def shutdown(self) -> None:
        # Only touch the engine if something actually opened it.
        if "db" in self.__dict__:
            await self.db.dispose()
