from __future__ import annotations

import asyncio
import threading
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient

from src.api.app import create_app
from src.application.use_cases.imports.dto import ImportOutcome, ImportRequest
from src.core.container import AppContainer
from src.domain.journal import TrackDetail
from src.domain.naming import EpisodeRef
from src.infrastructure import probing
from src.settings.config import Settings
from tests.api.conftest import (
    TOKEN,
    VIDEO_ONLY,
    StubHandler,
    _client_for,
    auth,
    await_job,
    drain,
)
from tests.conftest import touch


def payload(layout: dict[str, Path], **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "job_id": uuid.uuid4().hex,
        "app": "radarr",
        "source_path": str(layout["source"]),
        "destination_path": str(layout["destination"]),
    }
    body.update(overrides)
    return body


def stub(container: AppContainer, fn: Any) -> StubHandler:
    """Swap the real use case for a stub. cached_property allows assignment."""
    handler = StubHandler(fn)
    container.handle_import = handler  # type: ignore[assignment]
    return handler


async def run_import(
    client: AsyncClient, container: AppContainer, body: dict[str, Any]
) -> dict[str, Any]:
    submitted = await client.post("/v1/import", json=body, headers=auth())
    assert submitted.status_code == 202, submitted.text
    await drain(container)
    return await await_job(client, body["job_id"])


async def result_of(
    client: AsyncClient, container: AppContainer, body: dict[str, Any]
) -> dict[str, Any]:
    job = await run_import(client, container, body)
    assert job["state"] == "succeeded", job
    outcome: dict[str, Any] = job["result"]
    return outcome


async def test_healthz_needs_no_token(client: AsyncClient) -> None:
    response = await client.get("/healthz")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


class TestAuth:
    async def test_missing_token_is_rejected(
        self, client: AsyncClient, layout: dict[str, Path]
    ) -> None:
        response = await client.post("/v1/import", json=payload(layout))

        assert response.status_code == 401

    async def test_wrong_token_is_rejected(
        self, client: AsyncClient, layout: dict[str, Path]
    ) -> None:
        response = await client.post(
            "/v1/import", json=payload(layout), headers={"Authorization": "Bearer nope"}
        )

        assert response.status_code == 401

    async def test_malformed_header_is_rejected(
        self, client: AsyncClient, layout: dict[str, Path]
    ) -> None:
        response = await client.post(
            "/v1/import", json=payload(layout), headers={"Authorization": TOKEN}
        )

        assert response.status_code == 401

    async def test_job_endpoints_need_a_token(self, client: AsyncClient) -> None:
        job_id = uuid.uuid4().hex

        assert (await client.get(f"/v1/jobs/{job_id}")).status_code == 401
        assert (await client.get(f"/v1/jobs/{job_id}/protocol")).status_code == 401

    async def test_open_instance_allows_anonymous(
        self,
        container: AppContainer,
        settings: Settings,
        layout: dict[str, Path],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(probing, "probe", lambda _p: VIDEO_ONLY)
        open_container = AppContainer(
            replace(settings, auth_token=None),
            history=container.history,
            jobs=container.jobs,
            worker_state=container.worker_state,
            settings_store=container.settings_store,
            env={},
        )
        app = create_app(open_container.settings, open_container)

        async for anonymous in _client_for(app):
            response = await anonymous.post("/v1/import", json=payload(layout))
            assert response.status_code == 202


class TestSubmit:
    async def test_submission_is_accepted_and_echoes_the_job_id(
        self, client: AsyncClient, layout: dict[str, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(probing, "probe", lambda _p: VIDEO_ONLY)
        body = payload(layout)

        response = await client.post("/v1/import", json=body, headers=auth())

        assert response.status_code == 202
        assert response.json()["id"] == body["job_id"]

    async def test_resubmitting_the_same_job_id_does_not_mux_twice(
        self, client: AsyncClient, container: AppContainer, layout: dict[str, Path]
    ) -> None:
        """A retry after a lost reply must re-attach, not queue a second mux."""
        handler = stub(container, lambda _r: ImportOutcome(move_status="DeferMove", reason="stub"))
        body = payload(layout)

        for _ in range(3):
            assert (await client.post("/v1/import", json=body, headers=auth())).status_code == 202
        await drain(container)
        await await_job(client, body["job_id"])

        assert handler.calls == 1

    async def test_reusing_a_job_id_for_another_import_is_a_409(
        self, client: AsyncClient, layout: dict[str, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(probing, "probe", lambda _p: VIDEO_ONLY)
        body = payload(layout)
        await client.post("/v1/import", json=body, headers=auth())

        clash = dict(body, destination_path=str(layout["movie"] / "Other (2024).mkv"))
        response = await client.post("/v1/import", json=clash, headers=auth())

        assert response.status_code == 409

    async def test_invalid_app_name_is_a_422(
        self, client: AsyncClient, layout: dict[str, Path]
    ) -> None:
        response = await client.post(
            "/v1/import", json=payload(layout, app="lidarr"), headers=auth()
        )

        assert response.status_code == 422

    async def test_missing_required_field_is_a_422(self, client: AsyncClient) -> None:
        response = await client.post("/v1/import", json={"app": "radarr"}, headers=auth())

        assert response.status_code == 422

    async def test_unusable_job_id_is_a_422(
        self, client: AsyncClient, layout: dict[str, Path]
    ) -> None:
        response = await client.post(
            "/v1/import", json=payload(layout, job_id="../../etc"), headers=auth()
        )

        assert response.status_code == 422


class TestImportOutcome:
    async def test_defers_when_there_is_nothing_to_embed(
        self,
        client: AsyncClient,
        container: AppContainer,
        layout: dict[str, Path],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(probing, "probe", lambda _p: VIDEO_ONLY)

        result = await result_of(client, container, payload(layout))

        assert result["move_status"] == "DeferMove"

    async def test_rejects_paths_outside_the_roots(
        self,
        client: AsyncClient,
        container: AppContainer,
        layout: dict[str, Path],
        tmp_path: Path,
    ) -> None:
        stray = touch(tmp_path / "elsewhere" / "video.mkv")

        result = await result_of(client, container, payload(layout, source_path=str(stray)))

        assert result["move_status"] == "DeferMove"
        assert "path rejected" in result["reason"]

    async def test_successful_mux_is_serialised_into_the_result(
        self, client: AsyncClient, container: AppContainer, layout: dict[str, Path]
    ) -> None:
        outcome = ImportOutcome(
            move_status="RenameRequested",
            reason="embedded 1 external track(s)",
            media_file=layout["destination"],
            extra_files=(layout["release"] / "leftover.srt",),
            prevent_extra_import=True,
            added_tracks=(TrackDetail(kind="subtitles", label="Russian", language="rus"),),
        )
        stub(container, lambda _r: outcome)

        result = await result_of(client, container, payload(layout))

        assert result["move_status"] == "RenameRequested"
        assert result["media_file"] == str(layout["destination"])
        assert result["prevent_extra_import"] is True
        assert [t["label"] for t in result["added_tracks"]] == ["Russian"]

    async def test_a_completed_job_links_to_its_history_row(
        self,
        client: AsyncClient,
        container: AppContainer,
        layout: dict[str, Path],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(probing, "probe", lambda _p: VIDEO_ONLY)
        body = payload(layout)

        job = await run_import(client, container, body)

        detail = await client.get(f"/v1/history/{job['history_id']}", headers=auth())
        assert detail.status_code == 200
        assert detail.json()["source_path"] == body["source_path"]

    async def test_unexpected_error_fails_the_job(
        self, client: AsyncClient, container: AppContainer, layout: dict[str, Path]
    ) -> None:
        """A genuine bug must not be disguised as a successful DeferMove."""

        def boom(_request: ImportRequest) -> ImportOutcome:
            raise RuntimeError("unexpected")

        stub(container, boom)

        job = await run_import(client, container, payload(layout))

        assert job["state"] == "failed"
        assert job["result"] is None
        assert "unexpected" in job["error"]

    async def test_sonarr_episode_is_derived_from_the_filename(
        self, client: AsyncClient, container: AppContainer, layout: dict[str, Path]
    ) -> None:
        handler = stub(container, lambda _r: ImportOutcome(move_status="DeferMove", reason="stub"))

        await run_import(
            client,
            container,
            payload(
                layout,
                app="sonarr",
                source_path=str(layout["release"] / "Show.S01E02E03.1080p-GRP.mkv"),
            ),
        )

        assert handler.requests[0].episode_ref == EpisodeRef(season=1, episodes=(2, 3))


class TestJobPolling:
    async def test_unknown_job_is_a_404_on_the_json_route(self, client: AsyncClient) -> None:
        response = await client.get(f"/v1/jobs/{uuid.uuid4().hex}", headers=auth())

        assert response.status_code == 404

    async def test_unknown_job_is_reported_in_the_body_on_the_protocol_route(
        self, client: AsyncClient
    ) -> None:
        """The shim cannot read status codes portably, so state goes in the body."""
        response = await client.get(
            f"/v1/jobs/{uuid.uuid4().hex}/protocol", params={"wait": 0}, headers=auth()
        )

        assert response.status_code == 200
        assert response.text.splitlines() == ["[MuxarrState] unknown"]

    async def test_protocol_route_returns_the_outcome_once_done(
        self, client: AsyncClient, container: AppContainer, layout: dict[str, Path]
    ) -> None:
        outcome = ImportOutcome(
            move_status="RenameRequested",
            reason="embedded 1 external track(s)",
            media_file=layout["destination"],
            prevent_extra_import=True,
        )
        stub(container, lambda _r: outcome)
        body = payload(layout)
        await client.post("/v1/import", json=body, headers=auth())
        await drain(container)

        response = await client.get(
            f"/v1/jobs/{body['job_id']}/protocol", params={"wait": 10}, headers=auth()
        )

        assert response.text.splitlines() == [
            "[MuxarrState] done",
            f"[MediaFile] {layout['destination']}",
            "[PreventExtraImport]",
            "[MoveStatus] RenameRequested",
        ]

    async def test_protocol_route_reports_a_failed_job(
        self, client: AsyncClient, container: AppContainer, layout: dict[str, Path]
    ) -> None:
        def boom(_request: ImportRequest) -> ImportOutcome:
            raise RuntimeError("unexpected")

        stub(container, boom)
        body = payload(layout)
        await client.post("/v1/import", json=body, headers=auth())
        await drain(container)

        response = await client.get(
            f"/v1/jobs/{body['job_id']}/protocol", params={"wait": 10}, headers=auth()
        )

        assert response.text.splitlines() == ["[MuxarrState] error"]

    async def test_poll_reports_running_while_the_mux_is_in_flight(
        self, client: AsyncClient, container: AppContainer, layout: dict[str, Path]
    ) -> None:
        started = threading.Event()
        release = threading.Event()

        def blocking(_request: ImportRequest) -> ImportOutcome:
            started.set()
            release.wait(timeout=10)
            return ImportOutcome(move_status="DeferMove", reason="stub")

        stub(container, blocking)
        body = payload(layout)
        await client.post("/v1/import", json=body, headers=auth())

        # The worker runs concurrently here, as it does in production; the mux
        # is on a thread so the event loop keeps serving polls.
        worker = asyncio.create_task(drain(container))
        try:
            await asyncio.to_thread(started.wait, 10)
            response = await client.get(
                f"/v1/jobs/{body['job_id']}/protocol", params={"wait": 0}, headers=auth()
            )
            assert response.text.splitlines() == ["[MuxarrState] running"]
        finally:
            release.set()
            await worker

        await await_job(client, body["job_id"])

    async def test_a_queued_job_polls_as_running(
        self, client: AsyncClient, layout: dict[str, Path]
    ) -> None:
        """Nothing has claimed it yet, but the shim must keep waiting, not fail."""
        body = payload(layout)
        await client.post("/v1/import", json=body, headers=auth())

        response = await client.get(
            f"/v1/jobs/{body['job_id']}/protocol", params={"wait": 0}, headers=auth()
        )

        assert response.text.splitlines() == ["[MuxarrState] running"]
