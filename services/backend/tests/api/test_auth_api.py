"""The UI login, the API key and the ways the auth settings relax them."""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from ipaddress import ip_network

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.app import create_app
from src.application.use_cases.auth.sessions import SESSION_LIFETIME, session_digest
from src.core.container import AppContainer
from src.db.session import DBManager
from src.settings.config import Settings
from tests.api.conftest import API_KEY, auth, make_container

BROWSER = {"X-Requested-With": "XMLHttpRequest"}
USER = {"username": "admin", "password": "correct-horse"}


async def _clients(
    container: AppContainer, *, client: tuple[str, int] = ("127.0.0.1", 50000)
) -> AsyncIterator[AsyncClient]:
    app = create_app(container.settings, container)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app, client=client)
        async with AsyncClient(transport=transport, base_url="http://muxarr") as made:
            yield made


async def _setup(client: AsyncClient) -> None:
    response = await client.post("/v1/auth/setup", json=USER, headers=BROWSER)
    assert response.status_code == 200, response.text


async def _login(client: AsyncClient, **overrides: str) -> int:
    response = await client.post("/v1/auth/login", json={**USER, **overrides}, headers=BROWSER)
    return response.status_code


class TestSetup:
    async def test_a_fresh_instance_asks_for_setup(self, client: AsyncClient) -> None:
        body = (await client.get("/v1/auth/status")).json()

        assert body["setup_required"] is True
        assert body["authenticated"] is False
        assert body["method"] == "forms"

    async def test_setup_signs_the_browser_in(self, client: AsyncClient) -> None:
        response = await client.post("/v1/auth/setup", json=USER, headers=BROWSER)

        assert response.status_code == 200, response.text
        assert response.json()["authenticated"] is True
        assert response.json()["username"] == "admin"
        cookie = response.headers["set-cookie"].lower()
        assert "httponly" in cookie
        assert "samesite=strict" in cookie
        assert (await client.get("/v1/settings")).status_code == 200

    async def test_it_only_runs_once(self, client: AsyncClient) -> None:
        await _setup(client)

        again = await client.post(
            "/v1/auth/setup", json={"username": "mallory", "password": "x" * 12}, headers=BROWSER
        )

        assert again.status_code == 409

    async def test_a_short_password_is_refused(self, client: AsyncClient) -> None:
        response = await client.post(
            "/v1/auth/setup", json={"username": "admin", "password": "short"}, headers=BROWSER
        )

        assert response.status_code == 422
        assert (await client.get("/v1/auth/status")).json()["setup_required"] is True

    async def test_it_needs_the_browser_header(self, client: AsyncClient) -> None:
        assert (await client.post("/v1/auth/setup", json=USER)).status_code == 403


class TestLogin:
    async def test_the_right_password_opens_a_session(self, client: AsyncClient) -> None:
        await _setup(client)
        client.cookies.clear()

        assert await _login(client) == 200
        assert (await client.get("/v1/system")).status_code == 200

    async def test_the_username_is_case_insensitive(self, client: AsyncClient) -> None:
        await _setup(client)
        client.cookies.clear()

        assert await _login(client, username="ADMIN") == 200

    @pytest.mark.parametrize("field", ["username", "password"])
    async def test_wrong_credentials_are_refused(self, client: AsyncClient, field: str) -> None:
        await _setup(client)
        client.cookies.clear()

        assert await _login(client, **{field: "wrong-wrong"}) == 401
        assert (await client.get("/v1/system")).status_code == 401

    async def test_the_anonymous_status_does_not_name_the_account(
        self, client: AsyncClient
    ) -> None:
        await _setup(client)
        client.cookies.clear()

        body = (await client.get("/v1/auth/status")).json()

        assert body["setup_required"] is False
        assert body["authenticated"] is False
        assert body["username"] is None

    async def test_logout_ends_the_session(self, client: AsyncClient) -> None:
        await _setup(client)

        response = await client.post("/v1/auth/logout", headers=BROWSER)

        assert response.status_code == 204
        assert (await client.get("/v1/system")).status_code == 401


class TestSessionCookie:
    async def test_a_write_needs_the_browser_header(self, client: AsyncClient) -> None:
        """The CSRF guard: a cross-site form cannot add a custom header."""
        await _setup(client)

        bare = await client.patch("/v1/settings", json={"dedupe": "off"})
        marked = await client.patch("/v1/settings", json={"dedupe": "off"}, headers=BROWSER)

        assert bare.status_code == 403
        assert marked.status_code == 200, marked.text

    async def test_an_expired_session_is_refused(
        self, client: AsyncClient, container: AppContainer
    ) -> None:
        await _setup(client)
        user = await container.users.first()
        assert user is not None
        await container.sessions.create(
            session_digest("stale"), user.id, datetime.now(UTC) - timedelta(minutes=1)
        )
        client.cookies.clear()
        client.cookies.set("muxarr_session", "stale")

        assert (await client.get("/v1/system")).status_code == 401

    async def test_an_ageing_session_is_renewed(
        self, client: AsyncClient, container: AppContainer
    ) -> None:
        await _setup(client)
        user = await container.users.first()
        assert user is not None
        await container.sessions.create(
            session_digest("ageing"), user.id, datetime.now(UTC) + timedelta(days=1)
        )
        client.cookies.clear()
        client.cookies.set("muxarr_session", "ageing")

        response = await client.get("/v1/system")

        assert response.status_code == 200
        assert "muxarr_session=ageing" in response.headers["set-cookie"]
        stored = await container.sessions.get(session_digest("ageing"), datetime.now(UTC))
        assert stored is not None
        assert stored.expires_at > datetime.now(UTC) + SESSION_LIFETIME - timedelta(minutes=1)


class TestChangeCredentials:
    async def test_it_needs_the_current_password(self, client: AsyncClient) -> None:
        await _setup(client)

        response = await client.put(
            "/v1/auth/credentials",
            json={"current_password": "nope-nope", "username": "admin", "password": "y" * 10},
            headers=BROWSER,
        )

        assert response.status_code == 401

    async def test_other_sessions_are_signed_out(self, container: AppContainer) -> None:
        async for first in _clients(container):
            async for second in _clients(container):
                await _setup(first)
                assert await _login(second) == 200

                response = await first.put(
                    "/v1/auth/credentials",
                    json={
                        "current_password": USER["password"],
                        "username": "root",
                        "password": "brand-new-password",
                    },
                    headers=BROWSER,
                )

                assert response.status_code == 200, response.text
                assert response.json() == {"username": "root"}
                assert (await first.get("/v1/system")).status_code == 200
                assert (await second.get("/v1/system")).status_code == 401


class TestEnvironmentCredentials:
    @pytest.fixture
    def pinned(self, settings: Settings, db: DBManager) -> AppContainer:
        return make_container(replace(settings, username="admin", password="from-compose"), db)

    async def test_they_can_sign_in_without_setup(self, pinned: AppContainer) -> None:
        async for client in _clients(pinned):
            status = (await client.get("/v1/auth/status")).json()
            assert status["setup_required"] is False
            assert status["credentials_locked"] is True
            assert await _login(client, password="from-compose") == 200

    async def test_setup_and_change_are_refused(self, pinned: AppContainer) -> None:
        async for client in _clients(pinned):
            assert (
                await client.post("/v1/auth/setup", json=USER, headers=BROWSER)
            ).status_code == 409
            changed = await client.put(
                "/v1/auth/credentials",
                json={"current_password": "from-compose", "username": "x", "password": "y" * 10},
                headers=auth(),
            )
            assert changed.status_code == 409

    async def test_a_restart_overwrites_the_stored_password(
        self, pinned: AppContainer, settings: Settings, db: DBManager
    ) -> None:
        """How a forgotten password is reset."""
        async for client in _clients(pinned):
            assert await _login(client, password="from-compose") == 200

        restarted = make_container(replace(settings, username="admin", password="reset-it-now"), db)
        async for client in _clients(restarted):
            assert await _login(client, password="from-compose") == 401
            assert await _login(client, password="reset-it-now") == 200


class TestApiKey:
    @pytest.fixture
    def generated(self, settings: Settings, db: DBManager) -> AppContainer:
        return make_container(replace(settings, api_key=None), db)

    async def test_one_is_generated_and_works(self, generated: AppContainer) -> None:
        async for client in _clients(generated):
            await _setup(client)
            body = (await client.get("/v1/settings/api-key")).json()

            assert re.fullmatch(r"[0-9a-f]{32}", body["api_key"])
            assert body["locked"] is False
            client.cookies.clear()
            assert (
                await client.get("/v1/system", headers={"X-Api-Key": body["api_key"]})
            ).status_code == 200

    async def test_it_survives_a_restart(
        self, generated: AppContainer, settings: Settings, db: DBManager
    ) -> None:
        first = await generated.api_key()
        restarted = make_container(replace(settings, api_key=None), db)

        assert await restarted.api_key() == first

    async def test_regenerating_retires_the_old_key(self, generated: AppContainer) -> None:
        async for client in _clients(generated):
            old = await generated.api_key()

            response = await client.post(
                "/v1/settings/api-key/regenerate", headers={"X-Api-Key": old}
            )

            new = response.json()["api_key"]
            assert response.status_code == 200
            assert new != old
            assert (await client.get("/v1/system", headers={"X-Api-Key": old})).status_code == 401
            assert (await client.get("/v1/system", headers={"X-Api-Key": new})).status_code == 200

    async def test_a_pinned_key_cannot_be_regenerated(self, client: AsyncClient) -> None:
        response = await client.post("/v1/settings/api-key/regenerate", headers=auth())

        assert response.status_code == 409
        assert (await client.get("/v1/settings/api-key", headers=auth())).json() == {
            "api_key": API_KEY,
            "locked": True,
        }

    async def test_the_key_needs_no_browser_header(self, client: AsyncClient) -> None:
        response = await client.patch("/v1/settings", json={"dedupe": "off"}, headers=auth())

        assert response.status_code == 200


class TestLocalAddresses:
    @pytest.fixture
    def relaxed(self, settings: Settings, db: DBManager) -> AppContainer:
        return make_container(replace(settings, auth_required="disabled_for_local_addresses"), db)

    @pytest.mark.parametrize("host", ["127.0.0.1", "192.168.1.20", "172.18.0.4", "::1"])
    async def test_a_local_caller_needs_no_login(self, relaxed: AppContainer, host: str) -> None:
        async for client in _clients(relaxed, client=(host, 50000)):
            assert (await client.get("/v1/system")).status_code == 200
            assert (await client.get("/v1/auth/status")).json()["authenticated"] is True

    async def test_a_remote_caller_still_does(self, relaxed: AppContainer) -> None:
        async for client in _clients(relaxed, client=("203.0.113.9", 50000)):
            assert (await client.get("/v1/system")).status_code == 401

    async def test_it_is_off_by_default(self, client: AsyncClient) -> None:
        assert (await client.get("/v1/system")).status_code == 401

    async def test_writes_still_need_the_browser_header(self, relaxed: AppContainer) -> None:
        async for client in _clients(relaxed):
            response = await client.patch("/v1/settings", json={"dedupe": "off"})

            assert response.status_code == 403

    async def test_a_forged_forwarded_for_changes_nothing(self, relaxed: AppContainer) -> None:
        async for client in _clients(relaxed, client=("203.0.113.9", 50000)):
            forged = {"X-Forwarded-For": "127.0.0.1"}

            assert (await client.get("/v1/system", headers=forged)).status_code == 401

    @pytest.mark.parametrize(
        ("forwarded", "expected"), [("203.0.113.9", 401), ("192.168.1.20", 200)]
    )
    async def test_behind_a_trusted_proxy_the_real_caller_counts(
        self, settings: Settings, db: DBManager, forwarded: str, expected: int
    ) -> None:
        """Otherwise every request through a proxy on a Docker network looks local."""
        trusted = replace(
            settings,
            auth_required="disabled_for_local_addresses",
            trusted_proxies=(ip_network("172.18.0.2"),),
        )
        async for client in _clients(make_container(trusted, db), client=("172.18.0.2", 50000)):
            headers = {"X-Forwarded-For": f"{forwarded}, 172.18.0.2"}

            assert (await client.get("/v1/system", headers=headers)).status_code == expected

    async def test_the_local_networks_can_be_redefined(
        self, settings: Settings, db: DBManager
    ) -> None:
        tailnet = replace(
            settings,
            auth_required="disabled_for_local_addresses",
            local_networks=(ip_network("100.64.0.0/10"),),
        )
        container = make_container(tailnet, db)
        async for client in _clients(container, client=("100.101.102.103", 50000)):
            assert (await client.get("/v1/system")).status_code == 200
        async for client in _clients(container, client=("192.168.1.20", 50000)):
            assert (await client.get("/v1/system")).status_code == 401


class TestExternal:
    async def test_setup_is_not_required(self, settings: Settings, db: DBManager) -> None:
        container = make_container(replace(settings, auth_method="external"), db)
        async for client in _clients(container, client=("203.0.113.9", 50000)):
            body = (await client.get("/v1/auth/status")).json()

            assert body["setup_required"] is False
            assert body["authenticated"] is True
