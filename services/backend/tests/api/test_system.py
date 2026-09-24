"""Worker liveness and queue depth, as the dashboard reads them."""

from __future__ import annotations

from dataclasses import replace

import pytest
from httpx import AsyncClient

from src.api.app import create_app
from src.application.use_cases.imports.dto import ImportRequest, fingerprint
from src.core.container import AppContainer
from src.db.session import DBManager
from src.domain.health import HealthIssue
from src.settings.config import Settings
from tests.api.conftest import _client_for, auth, make_container


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


class TestHealth:
    async def test_a_silent_worker_is_an_error(self, client: AsyncClient) -> None:
        health = (await client.get("/v1/system", headers=auth())).json()["health"]

        assert [(i["level"], i["code"]) for i in health] == [("error", "worker_offline")]

    async def test_a_healthy_setup_reports_nothing(
        self, client: AsyncClient, container: AppContainer
    ) -> None:
        await container.worker_state.heartbeat()

        assert (await client.get("/v1/system", headers=auth())).json()["health"] == []

    async def test_the_workers_own_checks_are_shown_most_severe_first(
        self, client: AsyncClient, container: AppContainer
    ) -> None:
        await container.worker_state.heartbeat()
        await container.worker_state.report(
            [
                HealthIssue("notice", "mkvmerge_outdated", "old"),
                HealthIssue("error", "read_root_missing", "/media is missing"),
            ]
        )

        health = (await client.get("/v1/system", headers=auth())).json()["health"]

        assert [i["code"] for i in health] == ["read_root_missing", "mkvmerge_outdated"]
        assert health[0]["message"] == "/media is missing"

    @pytest.mark.parametrize(
        ("changes", "code"),
        [
            ({"auth_method": "external"}, "login_off"),
            ({"auth_required": "disabled_for_local_addresses"}, "proxies_untrusted"),
            ({"container_mode": "web"}, "sqlite_split"),
        ],
    )
    async def test_risky_configuration_is_called_out(
        self, settings: Settings, db: DBManager, changes: dict[str, str], code: str
    ) -> None:
        container = make_container(replace(settings, **changes), db)  # type: ignore[arg-type]
        await container.worker_state.heartbeat()
        async for client in _client_for(create_app(container.settings, container)):
            health = (await client.get("/v1/system", headers=auth())).json()["health"]

            assert [i["code"] for i in health] == [code]
