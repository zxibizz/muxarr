from __future__ import annotations

import threading
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from muxarr import pipeline, probe, server
from muxarr.config import Settings
from muxarr.discovery import EpisodeRef
from muxarr.models import MediaInfo, Track
from muxarr.pipeline import ImportOutcome
from tests.conftest import touch

TOKEN = "s3cret-token"

VIDEO_ONLY = MediaInfo(
    path=Path("/x.mkv"),
    container="Matroska",
    tracks=(Track(index=0, kind="video", codec_id="V_MPEG4/ISO/AVC"),),
)


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
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    # Context-managed on purpose: without it TestClient tears down its portal
    # after every request, cancelling the background job task mid-flight.
    with TestClient(server.create_app(settings)) as test_client:
        yield test_client


def payload(layout: dict[str, Path], **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "job_id": uuid.uuid4().hex,
        "app": "radarr",
        "source_path": str(layout["source"]),
        "destination_path": str(layout["destination"]),
    }
    body.update(overrides)
    return body


def auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}"}


def await_job(client: TestClient, job_id: str) -> dict[str, Any]:
    """Long-poll one job to completion."""
    response = client.get(f"/v1/jobs/{job_id}", params={"wait": 10}, headers=auth())
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    assert body["state"] in {"succeeded", "failed"}, f"job never settled: {body}"
    return body


def run_import(client: TestClient, body: dict[str, Any]) -> dict[str, Any]:
    submitted = client.post("/v1/import", json=body, headers=auth())
    assert submitted.status_code == 202, submitted.text
    return await_job(client, body["job_id"])


def result_of(client: TestClient, body: dict[str, Any]) -> dict[str, Any]:
    job = run_import(client, body)
    assert job["state"] == "succeeded", job
    outcome: dict[str, Any] = job["result"]
    return outcome


def test_healthz_needs_no_token(client: TestClient) -> None:
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


class TestAuth:
    def test_missing_token_is_rejected(self, client: TestClient, layout: dict[str, Path]) -> None:
        response = client.post("/v1/import", json=payload(layout))

        assert response.status_code == 401

    def test_wrong_token_is_rejected(self, client: TestClient, layout: dict[str, Path]) -> None:
        response = client.post(
            "/v1/import", json=payload(layout), headers={"Authorization": "Bearer nope"}
        )

        assert response.status_code == 401

    def test_malformed_header_is_rejected(
        self, client: TestClient, layout: dict[str, Path]
    ) -> None:
        response = client.post(
            "/v1/import", json=payload(layout), headers={"Authorization": TOKEN}
        )

        assert response.status_code == 401

    def test_job_endpoints_need_a_token(self, client: TestClient) -> None:
        job_id = uuid.uuid4().hex

        assert client.get(f"/v1/jobs/{job_id}").status_code == 401
        assert client.get(f"/v1/jobs/{job_id}/protocol").status_code == 401

    def test_open_instance_allows_anonymous(
        self, tmp_path: Path, layout: dict[str, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(probe, "probe", lambda _p: VIDEO_ONLY)
        open_settings = Settings(
            read_roots=(tmp_path / "downloads", tmp_path / "library"), auth_token=None
        )
        with TestClient(server.create_app(open_settings)) as anonymous:
            response = anonymous.post("/v1/import", json=payload(layout))

        assert response.status_code == 202


class TestSubmit:
    def test_submission_is_accepted_and_echoes_the_job_id(
        self, client: TestClient, layout: dict[str, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(probe, "probe", lambda _p: VIDEO_ONLY)
        body = payload(layout)

        response = client.post("/v1/import", json=body, headers=auth())

        assert response.status_code == 202
        assert response.json()["id"] == body["job_id"]

    def test_resubmitting_the_same_job_id_does_not_mux_twice(
        self, client: TestClient, layout: dict[str, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A retry after a lost reply must re-attach, not start a second mux."""
        calls = 0

        def counting(*_a: object, **_k: object) -> ImportOutcome:
            nonlocal calls
            calls += 1
            return ImportOutcome(move_status="DeferMove", reason="stub")

        monkeypatch.setattr(server, "handle_import", counting)
        body = payload(layout)

        for _ in range(3):
            assert client.post("/v1/import", json=body, headers=auth()).status_code == 202
        await_job(client, body["job_id"])

        assert calls == 1

    def test_reusing_a_job_id_for_another_import_is_a_409(
        self, client: TestClient, layout: dict[str, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(probe, "probe", lambda _p: VIDEO_ONLY)
        body = payload(layout)
        client.post("/v1/import", json=body, headers=auth())

        clash = dict(body, destination_path=str(layout["movie"] / "Other (2024).mkv"))
        response = client.post("/v1/import", json=clash, headers=auth())

        assert response.status_code == 409

    def test_invalid_app_name_is_a_422(
        self, client: TestClient, layout: dict[str, Path]
    ) -> None:
        response = client.post(
            "/v1/import", json=payload(layout, app="lidarr"), headers=auth()
        )

        assert response.status_code == 422

    def test_missing_required_field_is_a_422(self, client: TestClient) -> None:
        response = client.post("/v1/import", json={"app": "radarr"}, headers=auth())

        assert response.status_code == 422

    def test_unusable_job_id_is_a_422(
        self, client: TestClient, layout: dict[str, Path]
    ) -> None:
        response = client.post(
            "/v1/import", json=payload(layout, job_id="../../etc"), headers=auth()
        )

        assert response.status_code == 422


class TestImportOutcome:
    def test_defers_when_there_is_nothing_to_embed(
        self, client: TestClient, layout: dict[str, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(probe, "probe", lambda _p: VIDEO_ONLY)

        assert result_of(client, payload(layout))["move_status"] == "DeferMove"

    def test_rejects_paths_outside_the_roots(
        self, client: TestClient, layout: dict[str, Path], tmp_path: Path
    ) -> None:
        stray = touch(tmp_path / "elsewhere" / "video.mkv")

        result = result_of(client, payload(layout, source_path=str(stray)))

        assert result["move_status"] == "DeferMove"
        assert "path rejected" in result["reason"]

    def test_successful_mux_is_serialised_into_the_result(
        self, client: TestClient, layout: dict[str, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        outcome = ImportOutcome(
            move_status="RenameRequested",
            reason="embedded 1 external track(s)",
            media_file=layout["destination"],
            extra_files=(layout["release"] / "leftover.srt",),
            prevent_extra_import=True,
            added_tracks=("subtitles:Russian",),
        )
        monkeypatch.setattr(pipeline, "handle_import", lambda *_a, **_k: outcome)
        monkeypatch.setattr(server, "handle_import", lambda *_a, **_k: outcome)

        result = result_of(client, payload(layout))

        assert result["move_status"] == "RenameRequested"
        assert result["media_file"] == str(layout["destination"])
        assert result["prevent_extra_import"] is True
        assert result["added_tracks"] == ["subtitles:Russian"]

    def test_a_completed_job_links_to_its_history_row(
        self, client: TestClient, layout: dict[str, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(probe, "probe", lambda _p: VIDEO_ONLY)
        body = payload(layout)

        job = run_import(client, body)

        detail = client.get(f"/v1/history/{job['history_id']}", headers=auth())
        assert detail.status_code == 200
        assert detail.json()["source_path"] == body["source_path"]

    def test_unexpected_error_fails_the_job(
        self, client: TestClient, layout: dict[str, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A genuine bug must not be disguised as a successful DeferMove."""

        def boom(*_a: object, **_k: object) -> ImportOutcome:
            raise RuntimeError("unexpected")

        monkeypatch.setattr(server, "handle_import", boom)

        job = run_import(client, payload(layout))

        assert job["state"] == "failed"
        assert job["result"] is None
        assert "unexpected" in job["error"]

    def test_sonarr_episode_is_derived_from_the_filename(
        self, client: TestClient, layout: dict[str, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: dict[str, Any] = {}

        def capture(request: Any, *_a: object, **_k: object) -> ImportOutcome:
            seen["episode"] = request.episode_ref
            return ImportOutcome(move_status="DeferMove", reason="stub")

        monkeypatch.setattr(server, "handle_import", capture)

        run_import(
            client,
            payload(
                layout,
                app="sonarr",
                source_path=str(layout["release"] / "Show.S01E02E03.1080p-GRP.mkv"),
            ),
        )

        assert seen["episode"] == EpisodeRef(season=1, episodes=(2, 3))


class TestJobPolling:
    def test_unknown_job_is_a_404_on_the_json_route(self, client: TestClient) -> None:
        response = client.get(f"/v1/jobs/{uuid.uuid4().hex}", headers=auth())

        assert response.status_code == 404

    def test_unknown_job_is_reported_in_the_body_on_the_protocol_route(
        self, client: TestClient
    ) -> None:
        """The shim cannot read status codes portably, so state goes in the body."""
        response = client.get(
            f"/v1/jobs/{uuid.uuid4().hex}/protocol", params={"wait": 0}, headers=auth()
        )

        assert response.status_code == 200
        assert response.text.splitlines() == ["[MuxarrState] unknown"]

    def test_protocol_route_returns_the_outcome_once_done(
        self, client: TestClient, layout: dict[str, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        outcome = ImportOutcome(
            move_status="RenameRequested",
            reason="embedded 1 external track(s)",
            media_file=layout["destination"],
            prevent_extra_import=True,
        )
        monkeypatch.setattr(server, "handle_import", lambda *_a, **_k: outcome)
        body = payload(layout)
        client.post("/v1/import", json=body, headers=auth())

        response = client.get(
            f"/v1/jobs/{body['job_id']}/protocol", params={"wait": 10}, headers=auth()
        )

        assert response.text.splitlines() == [
            "[MuxarrState] done",
            f"[MediaFile] {layout['destination']}",
            "[PreventExtraImport]",
            "[MoveStatus] RenameRequested",
        ]

    def test_protocol_route_reports_a_failed_job(
        self, client: TestClient, layout: dict[str, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def boom(*_a: object, **_k: object) -> ImportOutcome:
            raise RuntimeError("unexpected")

        monkeypatch.setattr(server, "handle_import", boom)
        body = payload(layout)
        client.post("/v1/import", json=body, headers=auth())

        response = client.get(
            f"/v1/jobs/{body['job_id']}/protocol", params={"wait": 10}, headers=auth()
        )

        assert response.text.splitlines() == ["[MuxarrState] error"]

    def test_poll_reports_running_while_the_mux_is_in_flight(
        self, client: TestClient, layout: dict[str, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        release = threading.Event()

        def blocking(*_a: object, **_k: object) -> ImportOutcome:
            release.wait(timeout=10)
            return ImportOutcome(move_status="DeferMove", reason="stub")

        monkeypatch.setattr(server, "handle_import", blocking)
        body = payload(layout)
        client.post("/v1/import", json=body, headers=auth())

        try:
            response = client.get(
                f"/v1/jobs/{body['job_id']}/protocol", params={"wait": 0}, headers=auth()
            )
            assert response.text.splitlines() == ["[MuxarrState] running"]
        finally:
            release.set()

        await_job(client, body["job_id"])
