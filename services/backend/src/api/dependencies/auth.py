"""Container access and the request guard.

Two ways in, as in the *arr apps: the API key (``X-Api-Key``, or the legacy
``Authorization: Bearer`` the first shims sent) for scripts, and a session
cookie for the UI. The auth settings can waive the login; the key always works.
"""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import Depends, HTTPException, Request, Response, status

from src.application.use_cases.auth.sessions import IssuedSession
from src.core.container import AppContainer
from src.domain.auth import client_address, login_required

SESSION_COOKIE = "muxarr_session"
# Cross-site pages cannot set a custom header without a CORS preflight, which
# this API never grants; requiring one on writes is the CSRF guard.
CSRF_HEADER = "X-Requested-With"
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


@dataclass(frozen=True, slots=True)
class Caller:
    via: Literal["api_key", "session", "open"]
    username: str | None = None
    session_token: str | None = None


def get_container(request: Request) -> AppContainer:
    container: AppContainer = request.app.state.container
    return container


def set_session_cookie(response: Response, request: Request, issued: IssuedSession) -> None:
    max_age = int((issued.expires_at - datetime.now(UTC)).total_seconds())
    response.set_cookie(
        SESSION_COOKIE,
        issued.token,
        max_age=max(max_age, 0),
        path="/",
        httponly=True,
        samesite="strict",
        secure=request.url.scheme == "https",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, samesite="strict")


def require_csrf_header(request: Request) -> None:
    if request.method not in _SAFE_METHODS and not request.headers.get(CSRF_HEADER):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=f"missing {CSRF_HEADER} header"
        )


async def identify(
    request: Request,
    response: Response,
    container: Annotated[AppContainer, Depends(get_container)],
) -> Caller | None:
    supplied = _supplied_key(request)
    if supplied is not None and _same(supplied, await container.api_key()):
        return Caller(via="api_key")

    token = request.cookies.get(SESSION_COOKIE)
    if token:
        resolved = await container.resolve_session.execute(token)
        if resolved is not None:
            if resolved.renewed is not None:
                set_session_cookie(response, request, resolved.renewed)
            return Caller(via="session", username=resolved.session.username, session_token=token)

    settings = container.settings
    client = client_address(
        request.client.host if request.client else None,
        ",".join(request.headers.getlist("x-forwarded-for")) or None,
        settings.trusted_proxies,
    )
    if not login_required(
        settings.auth_method, settings.auth_required, client, settings.local_networks
    ):
        return Caller(via="open")
    return None


async def authorise(
    request: Request, caller: Annotated[Caller | None, Depends(identify)]
) -> Caller:
    if caller is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid or missing credentials"
        )
    if caller.via != "api_key":
        require_csrf_header(request)
    return caller


def _supplied_key(request: Request) -> str | None:
    key = request.headers.get("X-Api-Key")
    if key:
        return key.strip()
    authorization = request.headers.get("Authorization", "")
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


def _same(supplied: str, expected: str) -> bool:
    # Constant-time, and on bytes: compare_digest rejects non-ASCII str outright.
    return hmac.compare_digest(supplied.encode("utf-8"), expected.encode("utf-8"))
