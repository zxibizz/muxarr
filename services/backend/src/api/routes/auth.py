"""Signing in to the UI, and the API key the shims present."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from src.api.dependencies.auth import (
    SESSION_COOKIE,
    Caller,
    authorise,
    clear_session_cookie,
    get_container,
    identify,
    require_csrf_header,
    set_session_cookie,
)
from src.core.container import AppContainer
from src.schemas.auth import ApiKeyView, AuthStatusView, Credentials, CredentialsChange, UserView

router = APIRouter(prefix="/v1", tags=["auth"])


@router.get("/auth/status", response_model=AuthStatusView)
async def auth_status(
    caller: Annotated[Caller | None, Depends(identify)],
    container: Annotated[AppContainer, Depends(get_container)],
) -> AuthStatusView:
    return await _status(container, caller)


@router.post(
    "/auth/setup", response_model=AuthStatusView, dependencies=[Depends(require_csrf_header)]
)
async def setup(
    body: Credentials,
    request: Request,
    response: Response,
    container: Annotated[AppContainer, Depends(get_container)],
) -> AuthStatusView:
    issued = await container.setup.execute(body.username, body.password)
    set_session_cookie(response, request, issued)
    return await _status(container, Caller(via="session"))


@router.post(
    "/auth/login", response_model=AuthStatusView, dependencies=[Depends(require_csrf_header)]
)
async def login(
    body: Credentials,
    request: Request,
    response: Response,
    container: Annotated[AppContainer, Depends(get_container)],
) -> AuthStatusView:
    issued = await container.login.execute(body.username, body.password)
    set_session_cookie(response, request, issued)
    return await _status(container, Caller(via="session"))


@router.post(
    "/auth/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf_header)],
)
async def logout(
    request: Request,
    response: Response,
    container: Annotated[AppContainer, Depends(get_container)],
) -> None:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        await container.logout.execute(token)
    clear_session_cookie(response)


@router.put("/auth/credentials", response_model=UserView)
async def change_credentials(
    body: CredentialsChange,
    caller: Annotated[Caller, Depends(authorise)],
    container: Annotated[AppContainer, Depends(get_container)],
) -> UserView:
    user = await container.change_credentials.execute(
        current_password=body.current_password,
        username=body.username,
        password=body.password,
        keep_token=caller.session_token,
    )
    return UserView(username=user.username)


@router.get("/settings/api-key", response_model=ApiKeyView, dependencies=[Depends(authorise)])
async def read_api_key(
    container: Annotated[AppContainer, Depends(get_container)],
) -> ApiKeyView:
    return ApiKeyView(api_key=await container.api_key(), locked=container.api_key_pinned)


@router.post(
    "/settings/api-key/regenerate", response_model=ApiKeyView, dependencies=[Depends(authorise)]
)
async def regenerate_api_key(
    container: Annotated[AppContainer, Depends(get_container)],
) -> ApiKeyView:
    return ApiKeyView(api_key=await container.regenerate_api_key(), locked=False)


async def _status(container: AppContainer, caller: Caller | None) -> AuthStatusView:
    settings = container.settings
    found = await container.auth_status.execute(settings.auth_method)
    return AuthStatusView(
        method=settings.auth_method,
        required=settings.auth_required,
        setup_required=found.setup_required,
        authenticated=caller is not None,
        username=found.username if caller is not None and caller.via == "session" else None,
        credentials_locked=container.credentials_pinned,
    )
