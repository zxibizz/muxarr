"""Contracts for the UI login and the API key."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class UserRecord:
    id: int
    username: str
    password_hash: str


@dataclass(frozen=True, slots=True)
class SessionRecord:
    user_id: int
    username: str
    expires_at: datetime


class UserRepository(Protocol):
    async def first(self) -> UserRecord | None:
        """The one user; muxarr has a single account, as the *arr apps do."""
        ...

    async def find(self, username: str) -> UserRecord | None:
        """Case-insensitive lookup."""
        ...

    async def save(self, username: str, password_hash: str) -> UserRecord:
        """Create the user, or replace the existing one's credentials."""
        ...


class SessionRepository(Protocol):
    async def create(self, digest: str, user_id: int, expires_at: datetime) -> None: ...

    async def get(self, digest: str, now: datetime) -> SessionRecord | None:
        """The session, unless it has expired."""
        ...

    async def extend(self, digest: str, expires_at: datetime) -> None: ...

    async def delete(self, digest: str) -> None: ...

    async def delete_for_user(self, user_id: int, *, keep: str | None = None) -> None:
        """Sign the user out everywhere, except the session ``keep``."""
        ...

    async def prune(self, now: datetime) -> int: ...


class ApiKeyRepository(Protocol):
    async def get(self) -> str | None: ...

    async def create_if_absent(self, candidate: str) -> str:
        """Store ``candidate`` unless a key already exists; return the stored key."""
        ...

    async def replace(self, key: str) -> None: ...


class PasswordHasher(Protocol):
    def hash(self, password: str) -> str: ...

    def verify(self, password: str, encoded: str) -> bool: ...

    def needs_rehash(self, encoded: str) -> bool: ...
