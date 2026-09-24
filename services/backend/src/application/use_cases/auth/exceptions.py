"""Raised by the auth use cases."""

from __future__ import annotations

from src.domain.errors import MuxarrError


class InvalidCredentialsError(MuxarrError):
    def __init__(self) -> None:
        super().__init__("invalid username or password")


class AlreadySetUpError(MuxarrError):
    def __init__(self) -> None:
        super().__init__("a user already exists; sign in instead")


class AuthLockedError(MuxarrError):
    """Pinned by an environment variable and so not editable over HTTP."""


class CredentialsRejectedError(MuxarrError):
    """The requested username or password does not meet the rules."""
