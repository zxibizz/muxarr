"""Composition root.

Built by both processes: the API uses the enqueue/await half, the worker uses
the execution half. Neither reaches for a global.
"""

from __future__ import annotations

from functools import cached_property

from src.application.interfaces.history import HistoryRepository
from src.application.interfaces.jobs import JobRepository, WorkerStateRepository
from src.application.use_cases.history.operations import (
    ClearHistoryUseCase,
    GetOperationUseCase,
    GetStatsUseCase,
    ListOperationsUseCase,
)
from src.application.use_cases.imports.await_job import AwaitJobUseCase
from src.application.use_cases.imports.enqueue_import import EnqueueImportUseCase
from src.application.use_cases.imports.handle_import import HandleImportUseCase
from src.application.use_cases.imports.run_job import RunImportJobUseCase
from src.application.use_cases.system.status import GetSystemStatusUseCase
from src.db.session import DBManager
from src.domain.paths import PathGuard
from src.infrastructure.filesystem.placement import FilesystemPlacement
from src.infrastructure.filesystem.track_discovery import FilesystemTrackDiscovery
from src.infrastructure.history.repository import SqlAlchemyHistoryRepository
from src.infrastructure.jobs.repository import SqlAlchemyJobRepository
from src.infrastructure.jobs.worker_state import SqlAlchemyWorkerStateRepository
from src.infrastructure.mkvtoolnix.muxer import MkvmergeMuxer
from src.infrastructure.probing import FallbackMediaProber
from src.settings.config import Settings
from src.worker.service import WORKER_STALE_AFTER, ImportWorker


class AppContainer:
    def __init__(
        self,
        settings: Settings,
        *,
        history: HistoryRepository | None = None,
        jobs: JobRepository | None = None,
        worker_state: WorkerStateRepository | None = None,
    ) -> None:
        self.settings = settings
        self._history_override = history
        self._jobs_override = jobs
        self._worker_state_override = worker_state

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
    def jobs(self) -> JobRepository:
        return self._jobs_override or SqlAlchemyJobRepository(self.db)

    @cached_property
    def worker_state(self) -> WorkerStateRepository:
        return self._worker_state_override or SqlAlchemyWorkerStateRepository(self.db)

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
    def enqueue_import(self) -> EnqueueImportUseCase:
        return EnqueueImportUseCase(self.jobs)

    @cached_property
    def await_job(self) -> AwaitJobUseCase:
        return AwaitJobUseCase(self.jobs)

    @cached_property
    def run_import_job(self) -> RunImportJobUseCase:
        return RunImportJobUseCase(
            jobs=self.jobs,
            history=self.history,
            handler=self.handle_import,
        )

    @cached_property
    def import_worker(self) -> ImportWorker:
        return ImportWorker(
            jobs=self.jobs,
            worker_state=self.worker_state,
            run_job=self.run_import_job,
            max_concurrent_muxes=self.settings.max_concurrent_muxes,
            job_ttl_seconds=self.settings.job_ttl_seconds,
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

    @cached_property
    def system_status(self) -> GetSystemStatusUseCase:
        return GetSystemStatusUseCase(
            jobs=self.jobs,
            worker_state=self.worker_state,
            stale_after_seconds=WORKER_STALE_AFTER,
            max_concurrent_muxes=self.settings.max_concurrent_muxes,
        )

    async def shutdown(self) -> None:
        # Only touch the engine if something actually opened it.
        if "db" in self.__dict__:
            await self.db.dispose()
