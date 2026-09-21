"""Worker liveness and queue depth, as the dashboard reads them."""

from __future__ import annotations

from httpx import AsyncClient

from src.application.use_cases.imports.dto import ImportRequest, fingerprint
from src.core.container import AppContainer
from tests.api.conftest import auth


async def test_needs_a_token(client: AsyncClient) -> None:
    """Unlike /healthz: the queue depth describes what the daemon is doing."""
    assert (await client.get("/v1/system")).status_code == 401
    assert (await client.get("/healthz")).status_code == 200


async def test_reports_version_worker_and_queue(client: AsyncClient) -> None:
    response = await client.get("/v1/system", headers=auth())

    assert response.status_code == 200
    body = response.json()
    assert body["version"]
    assert body["worker"]["max_concurrent_muxes"] == 1
    assert body["worker"]["stale_after_seconds"] > 0
    assert body["queue"] == {"pending": 0, "running": 0, "succeeded": 0, "failed": 0}


class TestWorkerLiveness:
    async def test_a_worker_that_never_ran_is_not_alive(self, client: AsyncClient) -> None:
        body = (await client.get("/v1/system", headers=auth())).json()

        assert body["worker"]["last_seen_at"] is None
        assert body["worker"]["alive"] is False

    async def test_a_recent_heartbeat_is_alive(
        self, client: AsyncClient, container: AppContainer
    ) -> None:
        await container.worker_state.heartbeat()

        body = (await client.get("/v1/system", headers=auth())).json()

        assert body["worker"]["last_seen_at"] is not None
        assert body["worker"]["alive"] is True

    async def test_healthz_agrees_with_the_system_report(
        self, client: AsyncClient, container: AppContainer
    ) -> None:
        """Both read the same use case; a divergence means one grew its own copy."""
        await container.worker_state.heartbeat()

        health = (await client.get("/healthz")).json()
        worker = (await client.get("/v1/system", headers=auth())).json()["worker"]

        assert health["worker_seen_at"] == worker["last_seen_at"]
        assert health["worker_alive"] == worker["alive"]


async def test_queue_counts_track_the_jobs_table(
    client: AsyncClient, container: AppContainer
) -> None:
    request = ImportRequest(
        app="radarr",
        source_path=container.settings.read_roots[0] / "a.mkv",
        destination_path=container.settings.read_roots[1] / "a.mkv",
    )
    await container.jobs.create_or_get("job-1", fingerprint({"a": "b"}), request)

    body = (await client.get("/v1/system", headers=auth())).json()

    assert body["queue"]["pending"] == 1
