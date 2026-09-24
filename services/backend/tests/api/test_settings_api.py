"""Reading and editing settings over HTTP.

The two properties worth pinning down: an environment-pinned field cannot be
changed here, and the AI key never comes back out.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from httpx import AsyncClient

from src.api.app import create_app
from src.core.container import AppContainer
from src.db.session import DBManager
from src.infrastructure.ai.openai_compat import OpenAICompatibleCompleterFactory
from src.infrastructure.history.repository import SqlAlchemyHistoryRepository
from src.infrastructure.jobs.repository import SqlAlchemyJobRepository
from src.infrastructure.jobs.worker_state import SqlAlchemyWorkerStateRepository
from src.infrastructure.settings.repository import SqlAlchemySettingsRepository
from src.settings.config import Settings
from tests.api.conftest import API_KEY, _client_for, auth


async def get_settings(client: AsyncClient) -> dict[str, Any]:
    response = await client.get("/v1/settings", headers=auth())
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


class TestRead:
    async def test_effective_values_are_reported(self, client: AsyncClient) -> None:
        body = await get_settings(client)

        assert body["dedupe"] == "language_codec"
        assert body["max_concurrent_muxes"] == 1
        assert body["locked"] == []

    async def test_it_needs_a_token(self, client: AsyncClient) -> None:
        assert (await client.get("/v1/settings")).status_code == 401


class TestWrite:
    async def test_a_change_is_persisted_and_echoed(self, client: AsyncClient) -> None:
        response = await client.patch("/v1/settings", json={"dedupe": "language"}, headers=auth())

        assert response.status_code == 200, response.text
        assert response.json()["dedupe"] == "language"
        assert (await get_settings(client))["dedupe"] == "language"

    async def test_untouched_fields_survive_a_later_write(self, client: AsyncClient) -> None:
        await client.patch("/v1/settings", json={"dedupe": "off"}, headers=auth())
        await client.patch("/v1/settings", json={"history_max_records": 5}, headers=auth())

        body = await get_settings(client)
        assert body["dedupe"] == "off"
        assert body["history_max_records"] == 5

    async def test_the_running_container_picks_the_change_up(
        self, client: AsyncClient, container: AppContainer
    ) -> None:
        """Without this the API would report a value nothing is acting on."""
        await client.patch("/v1/settings", json={"max_external_tracks": 3}, headers=auth())

        assert container.settings.max_external_tracks == 3
        assert container.settings.selection_policy.max_external_tracks == 3

    async def test_an_out_of_range_value_is_refused(self, client: AsyncClient) -> None:
        response = await client.patch(
            "/v1/settings", json={"max_concurrent_muxes": 0}, headers=auth()
        )

        assert response.status_code == 422

    async def test_an_unknown_field_is_refused(self, client: AsyncClient) -> None:
        response = await client.patch("/v1/settings", json={"db_url": "x"}, headers=auth())

        assert response.status_code == 422

    async def test_enabling_ai_without_a_model_is_refused(self, client: AsyncClient) -> None:
        response = await client.patch("/v1/settings", json={"ai_mode": "fallback"}, headers=auth())

        assert response.status_code == 422
        assert "ai_model" in response.json()["detail"]

    async def test_keep_lists_are_normalised_and_echoed(
        self, client: AsyncClient, container: AppContainer
    ) -> None:
        response = await client.patch(
            "/v1/settings", json={"keep_audio_languages": ["en", "ja"]}, headers=auth()
        )

        assert response.status_code == 200, response.text
        assert response.json()["keep_audio_languages"] == ["eng", "jpn"]
        assert container.settings.selection_policy.keep_audio_languages == {"eng", "jpn"}

    async def test_an_unknown_language_is_refused(self, client: AsyncClient) -> None:
        response = await client.patch(
            "/v1/settings", json={"keep_subtitle_languages": ["zzz"]}, headers=auth()
        )

        assert response.status_code == 422

    async def test_null_clears_a_keep_list(self, client: AsyncClient) -> None:
        await client.patch("/v1/settings", json={"keep_audio_languages": ["eng"]}, headers=auth())
        await client.patch("/v1/settings", json={"keep_audio_languages": None}, headers=auth())

        assert (await get_settings(client))["keep_audio_languages"] == []


class TestSecrets:
    async def test_the_key_is_never_returned(self, client: AsyncClient) -> None:
        await client.patch(
            "/v1/settings",
            json={"ai_mode": "fallback", "ai_model": "tiny", "ai_api_key": "sk-secret"},
            headers=auth(),
        )

        response = await client.get("/v1/settings", headers=auth())

        assert "sk-secret" not in response.text
        assert response.json()["ai_api_key_set"] is True

    async def test_an_omitted_key_is_left_alone(self, client: AsyncClient) -> None:
        await client.patch(
            "/v1/settings",
            json={"ai_mode": "fallback", "ai_model": "tiny", "ai_api_key": "sk-secret"},
            headers=auth(),
        )

        await client.patch("/v1/settings", json={"ai_model": "small"}, headers=auth())

        assert (await get_settings(client))["ai_api_key_set"] is True

    async def test_an_explicit_null_clears_the_key(self, client: AsyncClient) -> None:
        await client.patch(
            "/v1/settings",
            json={"ai_mode": "fallback", "ai_model": "tiny", "ai_api_key": "sk-secret"},
            headers=auth(),
        )

        await client.patch("/v1/settings", json={"ai_api_key": None}, headers=auth())

        assert (await get_settings(client))["ai_api_key_set"] is False


class TestEnvironmentLock:
    @pytest.fixture
    async def pinned(self, settings: Settings, db: DBManager) -> AppContainer:
        return AppContainer(
            settings,
            history=SqlAlchemyHistoryRepository(db),
            jobs=SqlAlchemyJobRepository(db),
            worker_state=SqlAlchemyWorkerStateRepository(db),
            settings_store=SqlAlchemySettingsRepository(db),
            env={"MUXARR_DEDUPE": "language"},
        )

    async def test_a_pinned_field_is_reported_as_locked(self, pinned: AppContainer) -> None:
        async for client in _client_for(create_app(pinned.settings, pinned)):
            assert (await get_settings(client))["locked"] == ["dedupe"]

    async def test_writing_a_pinned_field_conflicts(self, pinned: AppContainer) -> None:
        """Compose stays the source of truth for whoever wrote it there."""
        async for client in _client_for(create_app(pinned.settings, pinned)):
            response = await client.patch("/v1/settings", json={"dedupe": "off"}, headers=auth())

            assert response.status_code == 409
            assert "MUXARR_DEDUPE" in response.json()["detail"]

    async def test_other_fields_stay_editable(self, pinned: AppContainer) -> None:
        async for client in _client_for(create_app(pinned.settings, pinned)):
            response = await client.patch(
                "/v1/settings", json={"history_max_records": 7}, headers=auth()
            )

            assert response.status_code == 200, response.text


class TestAiProbe:
    @staticmethod
    def _client_with(handler: Any, settings: Settings, db: DBManager) -> AppContainer:
        return AppContainer(
            settings,
            history=SqlAlchemyHistoryRepository(db),
            jobs=SqlAlchemyJobRepository(db),
            worker_state=SqlAlchemyWorkerStateRepository(db),
            settings_store=SqlAlchemySettingsRepository(db),
            completers=OpenAICompatibleCompleterFactory(httpx.MockTransport(handler)),
            env={},
        )

    async def test_a_reachable_provider_reports_ok(self, settings: Settings, db: DBManager) -> None:
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"choices": [{"message": {"content": '{"ok": true}'}}]})

        container = self._client_with(handler, settings, db)
        async for client in _client_for(create_app(container.settings, container)):
            response = await client.post(
                "/v1/settings/ai/test",
                json={"base_url": "https://api.example.com/v1", "model": "tiny"},
                headers=auth(),
            )

            assert response.status_code == 200, response.text
            assert response.json()["ok"] is True

    async def test_a_rejected_key_reports_the_provider_error(
        self, settings: Settings, db: DBManager
    ) -> None:
        """A 200 with ok=false: the button reports, it does not fail the request."""

        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(401, text="invalid api key")

        container = self._client_with(handler, settings, db)
        async for client in _client_for(create_app(container.settings, container)):
            response = await client.post(
                "/v1/settings/ai/test",
                json={"base_url": "https://api.example.com/v1", "model": "tiny"},
                headers=auth(),
            )

            assert response.status_code == 200, response.text
            body = response.json()
            assert body["ok"] is False
            assert "invalid api key" in body["message"]

    async def test_the_submitted_key_is_used_over_the_stored_one(
        self, settings: Settings, db: DBManager
    ) -> None:
        seen: list[str | None] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request.headers.get("Authorization"))
            return httpx.Response(200, json={"choices": [{"message": {"content": '{"ok": true}'}}]})

        stored = Settings(
            read_roots=settings.read_roots,
            api_key=API_KEY,
            db_url=settings.db_url,
            ai_api_key="sk-stored",
        )
        container = self._client_with(handler, stored, db)
        async for client in _client_for(create_app(container.settings, container)):
            await client.post(
                "/v1/settings/ai/test",
                json={
                    "base_url": "https://api.example.com/v1",
                    "model": "tiny",
                    "api_key": "sk-typed",
                },
                headers=auth(),
            )
            await client.post(
                "/v1/settings/ai/test",
                json={"base_url": "https://api.example.com/v1", "model": "tiny"},
                headers=auth(),
            )

        assert seen == ["Bearer sk-typed", "Bearer sk-stored"]
