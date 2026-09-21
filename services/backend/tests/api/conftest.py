"""Shared API-test wiring.

Everything runs on one event loop via ``httpx.AsyncClient``: the in-memory
SQLite engine, the request handlers and the background job task all have to
share a loop, which ``TestClient``'s portal thread does not give us.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.api.app import create_app
from src.application.use_cases.imports.dto import ImportOutcome, ImportRequest
from src.core.container import AppContainer
from src.db.session import DBManager
from src.domain.media import MediaInfo, Track
from src.infrastructure.history.repository import SqlAlchemyHistoryRepository
from src.infrastructure.jobs.repository import SqlAlchemyJobRepository
from src.infrastructure.jobs.worker_state import SqlAlchemyWorkerStateRepository
from src.settings.config import Settings
from tests.conftest import touch

TOKEN = "s3cret-token"

VIDEO_ONLY = MediaInfo(
    path=Path("/x.mkv"),
    container="Matroska",
    tracks=(Track(index=0, kind="video", codec_id="V_MPEG4/ISO/AVC"),),
)


class StubHandler:
    """Stands in for HandleImportUseCase; counts calls and records requests."""

    def __init__(self, fn: Callable[[ImportRequest], ImportOutcome]) -> None:
        self._fn = fn
        self.calls = 0
        self.requests: list[ImportRequest] = []

    def execute(self, request: ImportRequest) -> ImportOutcome:
        self.calls += 1
        self.requests.append(request)
        return self._fn(request)


def auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def layout(tmp_path: Path) -> dict[str, Path]:
    release = tmp_path / "downloads" / "Movie.2024-GRP"
    movie = tmp_path / "library" / "Movie (2024)"
    release.mkdir(parents=True)
    movie.mkdir(parents=True)
    return {
        "source": touch(release / "Movie.2024-GRP.mkv", b"video"),
        "destination": movie / "Movie (2024).mkv",
        "movie": movie,
        "release": release,
    }


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        read_roots=(tmp_path / "downloads", tmp_path / "library"),
        auth_token=TOKEN,
        db_url="sqlite+aiosqlite:///:memory:",
    )


@pytest.fixture
async def container(settings: Settings, db: DBManager) -> AppContainer:
    # Every repository is pinned to the fixture's engine, so the container never
    # opens a second (and separate) in-memory database of its own.
    return AppContainer(
        settings,
        history=SqlAlchemyHistoryRepository(db),
        jobs=SqlAlchemyJobRepository(db),
        worker_state=SqlAlchemyWorkerStateRepository(db),
    )


async def drain(container: AppContainer) -> int:
    """Run every queued job, as the worker process would.

    Explicit rather than spawning a real worker: the tests then assert on a
    settled queue instead of racing a poll interval.
    """
    ran = 0
    while (job := await container.jobs.claim_next()) is not None:
        await container.run_import_job.execute(job)
        ran += 1
    return ran


@pytest.fixture
async def client(container: AppContainer) -> AsyncIterator[AsyncClient]:
    async for made in _client_for(create_app(container.settings, container)):
        yield made


async def _client_for(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://muxarr") as made:
            yield made


async def await_job(client: AsyncClient, job_id: str) -> dict[str, Any]:
    """Read one settled job."""
    response = await client.get(f"/v1/jobs/{job_id}", params={"wait": 10}, headers=auth())
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    assert body["state"] in {"succeeded", "failed"}, f"job never settled: {body}"
    return body
