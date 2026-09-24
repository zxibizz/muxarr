"""Auth wire models."""

from __future__ import annotations

from pydantic import BaseModel

from src.domain.enums import AuthMethod, AuthRequired
from src.schemas.base import WireModel


class AuthStatusView(WireModel):
    method: AuthMethod
    required: AuthRequired
    # No user yet: the UI must offer the setup screen before anything else.
    setup_required: bool
    authenticated: bool
    # Only for a session: nobody is "signed in as" anyone through a key or an open door.
    username: str | None
    credentials_locked: bool


class Credentials(BaseModel):
    model_config = {"extra": "forbid"}

    username: str
    password: str


class CredentialsChange(BaseModel):
    model_config = {"extra": "forbid"}

    current_password: str
    username: str
    password: str


class UserView(WireModel):
    username: str


class ApiKeyView(WireModel):
    api_key: str
    # Pinned by MUXARR_API_KEY: shown, but not regenerable here.
    locked: bool
