"""Container access and the bearer-token guard.

The container is stashed on ``app.state`` by the factory; routes reach it only
through :func:`get_container`.
"""

from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status

from src.core.container import AppContainer


def get_container(request: Request) -> AppContainer:
    container: AppContainer = request.app.state.container
    return container


def authorise(
    container: Annotated[AppContainer, Depends(get_container)],
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    token = container.settings.auth_token
    if token is None:
        return
    supplied = ""
    if authorization and authorization.lower().startswith("bearer "):
        supplied = authorization[7:].strip()
    # Constant-time: a plain == leaks the token prefix through timing.
    if not hmac.compare_digest(supplied, token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid or missing token"
        )
