"""The log a job leaves behind.

Both copies matter: the one on the job row is what the UI follows while a remux
is still running, and the one on the operation is what survives the job's TTL.
"""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path

import pytest

from src.application.interfaces.jobs import JobRecord
from src.application.use_cases.imports import run_job as run_job_module
from src.application.use_cases.imports.dto import ImportOutcome, ImportRequest, fingerprint
from src.application.use_cases.imports.run_job import RunImportJobUseCase
from src.core.logging import get_logger
from src.db.session import DBManager
from src.domain.enums import LogComponent
from src.infrastructure.history.repository import SqlAlchemyHistoryRepository
from src.infrastructure.jobs.repository import SqlAlchemyJobRepository

log = get_logger(LogComponent.USECASE_IMPORT)

REQUEST = ImportRequest(
    app="radarr",
    source_path=Path("/downloads/a.mkv"),
    destination_path=Path("/library/a.mkv"),
)
FINGERPRINT = fingerprint({"source_path": "/downloads/a.mkv"})


class StubHandler:
    """Stands in for HandleImportUseCase, and like it runs on a worker thread."""

    def __init__(
        self, error: Exception | None = None, block: threading.Event | None = None
    ) -> None:
        self._error = error
        self._block = block

    def execute(self, request: ImportRequest) -> ImportOutcome:
        log.bind(stage="selection").info("embedding subtitles Russian")
        if self._block is not None:
            self._block.wait(timeout=5)
        if self._error is not None:
            raise self._error
        return ImportOutcome(move_status="RenameRequested", reason="embedded 1 external track(s)")


@pytest.fixture
def jobs(db: DBManager) -> SqlAlchemyJobRepository:
    return SqlAlchemyJobRepository(db)


def use_case(
    jobs: SqlAlchemyJobRepository,
    history: SqlAlchemyHistoryRepository,
    handler: StubHandler,
    limit: int = 100,
) -> RunImportJobUseCase:
    return RunImportJobUseCase(
        jobs=jobs,
        history=history,
        handler=handler,  # type: ignore[arg-type]
        log_max_entries=limit,
    )


async def claim(jobs: SqlAlchemyJobRepository) -> JobRecord:
    await jobs.create_or_get("job-1", FINGERPRINT, REQUEST)
    claimed = await jobs.claim_next()
    assert claimed is not None
    return claimed


async def test_the_log_lands_on_the_operation(
    jobs: SqlAlchemyJobRepository, history: SqlAlchemyHistoryRepository
) -> None:
    job = await claim(jobs)

    await use_case(jobs, history, StubHandler()).execute(job)

    settled = await jobs.get("job-1")
    assert settled is not None
    assert settled.history_id is not None
    operation = await history.get(settled.history_id)
    assert operation is not None
    messages = [entry.message for entry in operation.log]
    assert "import started" in messages
    assert "embedding subtitles Russian" in messages
    assert [e.stage for e in operation.log if e.stage] == ["selection"]


async def test_a_failed_job_keeps_its_log(
    jobs: SqlAlchemyJobRepository, history: SqlAlchemyHistoryRepository
) -> None:
    """A job that breaks the daemon writes no history row, so its own copy is all there is."""
    job = await claim(jobs)

    await use_case(jobs, history, StubHandler(error=RuntimeError("boom"))).execute(job)

    settled = await jobs.get("job-1")
    assert settled is not None
    assert settled.state == "failed"
    assert (await history.list()).total == 0
    messages = [e.message for e in settled.log]
    assert "embedding subtitles Russian" in messages
    assert "import job failed" in messages


async def test_the_log_is_published_while_the_import_is_still_running(
    jobs: SqlAlchemyJobRepository,
    history: SqlAlchemyHistoryRepository,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(run_job_module, "FLUSH_INTERVAL", 0.01)
    release = threading.Event()
    job = await claim(jobs)

    task = asyncio.create_task(use_case(jobs, history, StubHandler(block=release)).execute(job))
    mid_run: list[str] = []
    # Well inside the handler's own 5s block, but generous for a loaded CI box.
    for _ in range(400):
        await asyncio.sleep(0.01)
        running = await jobs.get("job-1")
        assert running is not None
        # The first flush can land before the worker thread has logged anything.
        if "embedding subtitles Russian" in (messages := [e.message for e in running.log]):
            mid_run = messages
            break
    release.set()
    await task

    assert "embedding subtitles Russian" in mid_run


async def test_a_limit_of_zero_stores_no_log(
    jobs: SqlAlchemyJobRepository, history: SqlAlchemyHistoryRepository
) -> None:
    job = await claim(jobs)

    await use_case(jobs, history, StubHandler(), limit=0).execute(job)

    settled = await jobs.get("job-1")
    assert settled is not None
    assert settled.history_id is not None
    operation = await history.get(settled.history_id)
    assert operation is not None
    assert operation.log == []
