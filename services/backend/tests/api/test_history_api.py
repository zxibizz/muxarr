from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient

from src.application.interfaces.history import HistoryRepository, NewOperation
from src.core.container import AppContainer
from src.domain.journal import LogEntry, TrackDetail
from src.infrastructure import probing
from tests.api.conftest import VIDEO_ONLY, auth, drain


async def run_import(
    client: AsyncClient, container: AppContainer, layout: dict[str, Path]
) -> dict[str, Any]:
    """Queue an import, run the worker, and read the settled job."""
    job_id = uuid.uuid4().hex
    await client.post(
        "/v1/import",
        json={
            "job_id": job_id,
            "app": "radarr",
            "source_path": str(layout["source"]),
            "destination_path": str(layout["destination"]),
        },
        headers=auth(),
    )
    await drain(container)
    response = await client.get(f"/v1/jobs/{job_id}", params={"wait": 10}, headers=auth())
    body: dict[str, Any] = response.json()
    assert body["state"] in {"succeeded", "failed"}, f"job never settled: {body}"
    return body


async def seed(store: HistoryRepository, **overrides: Any) -> int:
    payload: dict[str, Any] = {
        "app": "radarr",
        "title": "Movie.2024-GRP.mkv",
        "move_status": "RenameRequested",
        "reason": "embedded 1 external track(s)",
        "source_path": "/downloads/x.mkv",
        "destination_path": "/library/x.mkv",
    }
    payload.update(overrides)
    return await store.record(NewOperation(**payload))


@pytest.fixture
def store(container: AppContainer) -> HistoryRepository:
    return container.history


class TestHistoryEndpoints:
    async def test_empty_history(self, client: AsyncClient) -> None:
        body = (await client.get("/v1/history", headers=auth())).json()

        assert body == {"items": [], "total": 0, "limit": 50, "offset": 0}

    async def test_lists_newest_first(self, client: AsyncClient, store: HistoryRepository) -> None:
        await seed(store, title="first.mkv")
        await seed(store, title="second.mkv")

        body = (await client.get("/v1/history", headers=auth())).json()

        assert [item["title"] for item in body["items"]] == ["second.mkv", "first.mkv"]

    async def test_filters_are_wired_through(
        self, client: AsyncClient, store: HistoryRepository
    ) -> None:
        await seed(store, app="sonarr", move_status="DeferMove")
        await seed(store, app="radarr", move_status="RenameRequested")

        body = (
            await client.get(
                "/v1/history",
                params={"app": "sonarr", "move_status": "DeferMove"},
                headers=auth(),
            )
        ).json()

        assert body["total"] == 1
        assert body["items"][0]["app"] == "sonarr"

    async def test_search_is_wired_through(
        self, client: AsyncClient, store: HistoryRepository
    ) -> None:
        await seed(store, title="Hanaori.mkv")
        await seed(store, title="Other.mkv")

        body = (await client.get("/v1/history", params={"q": "Hanaori"}, headers=auth())).json()

        assert body["total"] == 1

    async def test_pagination(self, client: AsyncClient, store: HistoryRepository) -> None:
        for index in range(5):
            await seed(store, title=f"{index}.mkv")

        body = (
            await client.get("/v1/history", params={"limit": 2, "offset": 1}, headers=auth())
        ).json()

        assert (body["total"], len(body["items"]), body["offset"]) == (5, 2, 1)

    async def test_limit_above_maximum_is_rejected(self, client: AsyncClient) -> None:
        response = await client.get("/v1/history", params={"limit": 10_000}, headers=auth())

        assert response.status_code == 422

    async def test_detail(self, client: AsyncClient, store: HistoryRepository) -> None:
        operation_id = await seed(
            store,
            added_tracks=[TrackDetail(kind="subtitles", label="Russian", source="ai")],
            log=[
                LogEntry(
                    ts="2026-01-01T00:00:00Z",
                    level="INFO",
                    component="usecase.import",
                    message="embedding subtitles Russian",
                    stage="selection",
                )
            ],
        )

        body = (await client.get(f"/v1/history/{operation_id}", headers=auth())).json()

        assert body["id"] == operation_id
        assert body["added_tracks"] == [
            {
                "kind": "subtitles",
                "label": "Russian",
                "language": "und",
                "name": None,
                "forced": False,
                "hearing_impaired": False,
                "variant": None,
                "file": "",
                "source": "ai",
            }
        ]
        assert [(e["stage"], e["message"]) for e in body["log"]] == [
            ("selection", "embedding subtitles Russian")
        ]

    async def test_detail_404(self, client: AsyncClient) -> None:
        assert (await client.get("/v1/history/999", headers=auth())).status_code == 404

    async def test_clear(self, client: AsyncClient, store: HistoryRepository) -> None:
        await seed(store)
        await seed(store)

        response = await client.delete("/v1/history", headers=auth())

        assert response.json() == {"deleted": 2}
        assert (await store.list()).total == 0

    async def test_history_requires_a_token(self, client: AsyncClient) -> None:
        assert (await client.get("/v1/history")).status_code == 401
        assert (await client.get("/v1/stats")).status_code == 401
        assert (await client.delete("/v1/history")).status_code == 401


class TestStatsEndpoint:
    async def test_stats(self, client: AsyncClient, store: HistoryRepository) -> None:
        await seed(
            store,
            added_tracks=[
                TrackDetail(kind="audio", label="a"),
                TrackDetail(kind="subtitles", label="b"),
            ],
        )
        await seed(store, move_status="DeferMove")

        body = (await client.get("/v1/stats", headers=auth())).json()

        assert body["total"] == 2
        assert body["muxed"] == 1
        assert body["deferred"] == 1
        assert body["tracks_added"] == 2


class TestRecording:
    @pytest.fixture(autouse=True)
    def _stub_probe(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(probing, "probe", lambda _p: VIDEO_ONLY)

    async def test_deferred_imports_are_recorded(
        self,
        client: AsyncClient,
        container: AppContainer,
        store: HistoryRepository,
        layout: dict[str, Path],
    ) -> None:
        """Deferrals are the common outcome and the main thing the UI explains."""
        await run_import(client, container, layout)

        page = await store.list()
        assert page.total == 1
        assert page.items[0].move_status == "DeferMove"
        assert "no external tracks" in page.items[0].reason
        assert page.items[0].title == "Movie.2024-GRP.mkv"

    async def test_duration_is_captured(
        self,
        client: AsyncClient,
        container: AppContainer,
        store: HistoryRepository,
        layout: dict[str, Path],
    ) -> None:
        await run_import(client, container, layout)

        items = (await store.list()).items
        assert items[0].duration_ms >= 0
        assert items[0].source_bytes == len(b"video")

    async def test_a_completed_job_reports_its_history_row(
        self,
        client: AsyncClient,
        container: AppContainer,
        store: HistoryRepository,
        layout: dict[str, Path],
    ) -> None:
        job = await run_import(client, container, layout)

        assert job["history_id"] == (await store.list()).items[0].id

    async def test_a_failing_history_write_does_not_break_the_import(
        self,
        client: AsyncClient,
        container: AppContainer,
        store: HistoryRepository,
        layout: dict[str, Path],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Losing a log row must never turn a good import into a failed one."""

        async def boom(**_kwargs: object) -> int:
            raise RuntimeError("disk full")

        monkeypatch.setattr(store, "record", boom)

        job = await run_import(client, container, layout)

        assert job["state"] == "succeeded"
        assert job["result"]["move_status"] == "DeferMove"
        assert job["history_id"] is None


async def test_healthz_reports_auth_state(client: AsyncClient) -> None:
    body = (await client.get("/healthz")).json()

    assert body["auth_required"] is True
