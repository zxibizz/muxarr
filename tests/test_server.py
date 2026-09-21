from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from muxarr import pipeline, probe, server
from muxarr.config import Settings
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
def client(settings: Settings) -> TestClient:
    return TestClient(server.create_app(settings))


def payload(layout: dict[str, Path], **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "app": "radarr",
        "source_path": str(layout["source"]),
        "destination_path": str(layout["destination"]),
        "library_path": str(layout["movie"]),
    }
    body.update(overrides)
    return body


def auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}"}


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

    def test_open_instance_allows_anonymous(
        self, tmp_path: Path, layout: dict[str, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(probe, "probe", lambda _p: VIDEO_ONLY)
        open_settings = Settings(
            read_roots=(tmp_path / "downloads", tmp_path / "library"), auth_token=None
        )
        response = TestClient(server.create_app(open_settings)).post(
            "/v1/import", json=payload(layout)
        )

        assert response.status_code == 200


class TestImportEndpoint:
    def test_defers_when_there_is_nothing_to_embed(
        self, client: TestClient, layout: dict[str, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(probe, "probe", lambda _p: VIDEO_ONLY)

        response = client.post("/v1/import", json=payload(layout), headers=auth())

        assert response.status_code == 200
        assert response.json()["move_status"] == "DeferMove"

    def test_rejects_paths_outside_the_roots(
        self, client: TestClient, layout: dict[str, Path], tmp_path: Path
    ) -> None:
        stray = touch(tmp_path / "elsewhere" / "video.mkv")

        response = client.post(
            "/v1/import", json=payload(layout, source_path=str(stray)), headers=auth()
        )

        body = response.json()
        assert response.status_code == 200
        assert body["move_status"] == "DeferMove"
        assert "path rejected" in body["reason"]

    def test_successful_mux_is_serialised_into_the_response(
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

        response = client.post("/v1/import", json=payload(layout), headers=auth())

        body = response.json()
        assert body["move_status"] == "RenameRequested"
        assert body["media_file"] == str(layout["destination"])
        assert body["prevent_extra_import"] is True
        assert body["added_tracks"] == ["subtitles:Russian"]

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

    def test_unexpected_error_surfaces_as_500(
        self, client: TestClient, layout: dict[str, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A genuine bug must not be disguised as a successful DeferMove."""

        def boom(*_a: object, **_k: object) -> ImportOutcome:
            raise RuntimeError("unexpected")

        monkeypatch.setattr(server, "handle_import", boom)

        with pytest.raises(RuntimeError):
            client.post("/v1/import", json=payload(layout), headers=auth())

    def test_sonarr_episode_fields_round_trip(
        self, client: TestClient, layout: dict[str, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: dict[str, Any] = {}

        def capture(request: Any, *_a: object, **_k: object) -> ImportOutcome:
            seen["season"] = request.season
            seen["episodes"] = request.episodes
            return ImportOutcome(move_status="DeferMove", reason="stub")

        monkeypatch.setattr(server, "handle_import", capture)

        client.post(
            "/v1/import",
            json=payload(layout, app="sonarr", season=1, episodes=[2, 3]),
            headers=auth(),
        )

        assert seen == {"season": 1, "episodes": (2, 3)}
