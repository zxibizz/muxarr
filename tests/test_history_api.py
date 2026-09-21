from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from muxarr import probe, server
from muxarr.config import Settings
from muxarr.history import HistoryStore
from muxarr.models import MediaInfo, Track
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
    }


@pytest.fixture
def store() -> HistoryStore:
    return HistoryStore()


@pytest.fixture
def client(tmp_path: Path, store: HistoryStore) -> Iterator[TestClient]:
    settings = Settings(
        read_roots=(tmp_path / "downloads", tmp_path / "library"),
        auth_token=TOKEN,
    )
    # Context-managed so the background job task survives the request that
    # queued it.
    with TestClient(server.create_app(settings, store)) as test_client:
        yield test_client


def auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}"}


def run_import(client: TestClient, layout: dict[str, Path]) -> dict[str, Any]:
    """Queue an import and block until it settles."""
    job_id = uuid.uuid4().hex
    client.post(
        "/v1/import",
        json={
            "job_id": job_id,
            "app": "radarr",
            "source_path": str(layout["source"]),
            "destination_path": str(layout["destination"]),
        },
        headers=auth(),
    )
    response = client.get(f"/v1/jobs/{job_id}", params={"wait": 10}, headers=auth())
    body: dict[str, Any] = response.json()
    assert body["state"] in {"succeeded", "failed"}, f"job never settled: {body}"
    return body


def seed(store: HistoryStore, **overrides: Any) -> int:
    payload: dict[str, Any] = {
        "app": "radarr",
        "title": "Movie.2024-GRP.mkv",
        "move_status": "RenameRequested",
        "reason": "embedded 1 external track(s)",
        "source_path": "/downloads/x.mkv",
        "destination_path": "/library/x.mkv",
    }
    payload.update(overrides)
    return store.record(**payload)


class TestHistoryEndpoints:
    def test_empty_history(self, client: TestClient) -> None:
        body = client.get("/v1/history", headers=auth()).json()

        assert body == {"items": [], "total": 0, "limit": 50, "offset": 0}

    def test_lists_newest_first(self, client: TestClient, store: HistoryStore) -> None:
        seed(store, title="first.mkv")
        seed(store, title="second.mkv")

        body = client.get("/v1/history", headers=auth()).json()

        assert [item["title"] for item in body["items"]] == ["second.mkv", "first.mkv"]

    def test_filters_are_wired_through(self, client: TestClient, store: HistoryStore) -> None:
        seed(store, app="sonarr", move_status="DeferMove")
        seed(store, app="radarr", move_status="RenameRequested")

        body = client.get(
            "/v1/history", params={"app": "sonarr", "move_status": "DeferMove"}, headers=auth()
        ).json()

        assert body["total"] == 1
        assert body["items"][0]["app"] == "sonarr"

    def test_search_is_wired_through(self, client: TestClient, store: HistoryStore) -> None:
        seed(store, title="Hanaori.mkv")
        seed(store, title="Other.mkv")

        body = client.get("/v1/history", params={"q": "Hanaori"}, headers=auth()).json()

        assert body["total"] == 1

    def test_pagination(self, client: TestClient, store: HistoryStore) -> None:
        for index in range(5):
            seed(store, title=f"{index}.mkv")

        body = client.get(
            "/v1/history", params={"limit": 2, "offset": 1}, headers=auth()
        ).json()

        assert (body["total"], len(body["items"]), body["offset"]) == (5, 2, 1)

    def test_limit_above_maximum_is_rejected(self, client: TestClient) -> None:
        response = client.get("/v1/history", params={"limit": 10_000}, headers=auth())

        assert response.status_code == 422

    def test_detail(self, client: TestClient, store: HistoryStore) -> None:
        operation_id = seed(store, added_tracks=["subtitles:Russian"])

        body = client.get(f"/v1/history/{operation_id}", headers=auth()).json()

        assert body["id"] == operation_id
        assert body["added_tracks"] == ["subtitles:Russian"]

    def test_detail_404(self, client: TestClient) -> None:
        assert client.get("/v1/history/999", headers=auth()).status_code == 404

    def test_clear(self, client: TestClient, store: HistoryStore) -> None:
        seed(store)
        seed(store)

        response = client.delete("/v1/history", headers=auth())

        assert response.json() == {"deleted": 2}
        assert store.list().total == 0

    def test_history_requires_a_token(self, client: TestClient) -> None:
        assert client.get("/v1/history").status_code == 401
        assert client.get("/v1/stats").status_code == 401
        assert client.delete("/v1/history").status_code == 401


class TestStatsEndpoint:
    def test_stats(self, client: TestClient, store: HistoryStore) -> None:
        seed(store, added_tracks=["a", "b"])
        seed(store, move_status="DeferMove")

        body = client.get("/v1/stats", headers=auth()).json()

        assert body["total"] == 2
        assert body["muxed"] == 1
        assert body["deferred"] == 1
        assert body["tracks_added"] == 2


class TestRecording:
    def test_deferred_imports_are_recorded(
        self,
        client: TestClient,
        store: HistoryStore,
        layout: dict[str, Path],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Deferrals are the common outcome and the main thing the UI explains."""
        monkeypatch.setattr(probe, "probe", lambda _p: VIDEO_ONLY)

        run_import(client, layout)

        page = store.list()
        assert page.total == 1
        assert page.items[0].move_status == "DeferMove"
        assert "no external tracks" in page.items[0].reason
        assert page.items[0].title == "Movie.2024-GRP.mkv"

    def test_duration_is_captured(
        self,
        client: TestClient,
        store: HistoryStore,
        layout: dict[str, Path],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(probe, "probe", lambda _p: VIDEO_ONLY)

        run_import(client, layout)

        assert store.list().items[0].duration_ms >= 0
        assert store.list().items[0].source_bytes == len(b"video")

    def test_a_completed_job_reports_its_history_row(
        self,
        client: TestClient,
        store: HistoryStore,
        layout: dict[str, Path],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(probe, "probe", lambda _p: VIDEO_ONLY)

        job = run_import(client, layout)

        assert job["history_id"] == store.list().items[0].id

    def test_a_failing_history_write_does_not_break_the_import(
        self,
        client: TestClient,
        store: HistoryStore,
        layout: dict[str, Path],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Losing a log row must never turn a good import into a failed one."""
        monkeypatch.setattr(probe, "probe", lambda _p: VIDEO_ONLY)

        def boom(**_kwargs: object) -> int:
            raise RuntimeError("disk full")

        monkeypatch.setattr(store, "record", boom)

        job = run_import(client, layout)

        assert job["state"] == "succeeded"
        assert job["result"]["move_status"] == "DeferMove"
        assert job["history_id"] is None


def test_healthz_reports_auth_state(client: TestClient) -> None:
    body = client.get("/healthz").json()

    assert body["auth_required"] is True
