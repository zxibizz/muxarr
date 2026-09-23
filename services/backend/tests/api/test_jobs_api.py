"""The jobs listing, which is how a job that never reached the history is read."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from httpx import AsyncClient

from src.core.container import AppContainer
from tests.api.conftest import auth, drain


async def queue(client: AsyncClient, layout: dict[str, Path]) -> str:
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
    return job_id


async def test_listing_is_empty_to_start(client: AsyncClient) -> None:
    body = (await client.get("/v1/jobs", headers=auth())).json()

    assert body == {"items": [], "total": 0, "limit": 20, "offset": 0}


async def test_a_queued_job_is_listed_with_its_title(
    client: AsyncClient, layout: dict[str, Path]
) -> None:
    job_id = await queue(client, layout)

    body = (await client.get("/v1/jobs", headers=auth())).json()

    assert body["total"] == 1
    item = body["items"][0]
    assert item["id"] == job_id
    assert item["state"] == "pending"
    assert item["title"] == layout["source"].name
    assert item["log"] == []


async def test_state_filter_is_wired_through(
    client: AsyncClient, container: AppContainer, layout: dict[str, Path]
) -> None:
    await queue(client, layout)
    await drain(container)

    pending = (await client.get("/v1/jobs", params={"state": "pending"}, headers=auth())).json()
    succeeded = (await client.get("/v1/jobs", params={"state": "succeeded"}, headers=auth())).json()

    assert pending["total"] == 0
    assert succeeded["total"] == 1


async def test_detail_carries_the_log(
    client: AsyncClient, container: AppContainer, layout: dict[str, Path]
) -> None:
    job_id = await queue(client, layout)
    await drain(container)

    body: dict[str, Any] = (await client.get(f"/v1/jobs/{job_id}/detail", headers=auth())).json()

    assert body["state"] == "succeeded"
    assert "import started" in [entry["message"] for entry in body["log"]]


async def test_detail_404(client: AsyncClient) -> None:
    assert (await client.get("/v1/jobs/unknown-job-id/detail", headers=auth())).status_code == 404


async def test_jobs_require_a_token(client: AsyncClient) -> None:
    assert (await client.get("/v1/jobs")).status_code == 401
