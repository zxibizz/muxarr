"""Signing in to the UI.

The cookie carries a random token; only its SHA-256 is stored, so reading the
sessions table does not let anyone sign in.
"""

from __future__ import annotations

import asyncio
import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from src.application.interfaces.auth import (
    PasswordHasher,
    SessionRecord,
    SessionRepository,
    UserRecord,
    UserRepository,
)
from src.application.use_cases.auth.exceptions import (
    AlreadySetUpError,
    AuthLockedError,
    CredentialsRejectedError,
    InvalidCredentialsError,
)
from src.core.logging import get_logger
from src.domain.auth import credentials_problem
from src.domain.enums import AuthMethod, LogComponent

log = get_logger(LogComponent.USECASE_AUTH)

SESSION_LIFETIME = timedelta(days=30)

_LOCKED = "the login is pinned by MUXARR_USERNAME/MUXARR_PASSWORD; change it there instead"


@dataclass(frozen=True, slots=True)
class IssuedSession:
    token: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class ResolvedSession:
    session: SessionRecord
    # Set when the expiry moved, so the caller can re-issue the cookie.
    renewed: IssuedSession | None = None


def session_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(UTC)


async def _issue(sessions: SessionRepository, user_id: int) -> IssuedSession:
    token = secrets.token_urlsafe(32)
    expires_at = _now() + SESSION_LIFETIME
    await sessions.create(session_digest(token), user_id, expires_at)
    return IssuedSession(token=token, expires_at=expires_at)


def _checked(username: str, password: str) -> str:
    problem = credentials_problem(username, password)
    if problem is not None:
        raise CredentialsRejectedError(problem)
    return username.strip()


class LoginUseCase:
    def __init__(
        self, *, users: UserRepository, sessions: SessionRepository, hasher: PasswordHasher
    ) -> None:
        self._users = users
        self._sessions = sessions
        self._hasher = hasher
        self._decoy: str | None = None

    async def execute(self, username: str, password: str) -> IssuedSession:
        user = await self._users.find(username)
        if user is None:
            # Hash anyway, so the response time does not reveal which usernames exist.
            if self._decoy is None:
                self._decoy = await asyncio.to_thread(self._hasher.hash, secrets.token_hex(8))
            await asyncio.to_thread(self._hasher.verify, password, self._decoy)
            log.warning("sign-in refused", username=username)
            raise InvalidCredentialsError
        if not await asyncio.to_thread(self._hasher.verify, password, user.password_hash):
            log.warning("sign-in refused", username=username)
            raise InvalidCredentialsError

        if self._hasher.needs_rehash(user.password_hash):
            rehashed = await asyncio.to_thread(self._hasher.hash, password)
            await self._users.save(user.username, rehashed)
        await self._sessions.prune(_now())
        log.info("signed in", username=user.username)
        return await _issue(self._sessions, user.id)


class LogoutUseCase:
    def __init__(self, *, sessions: SessionRepository) -> None:
        self._sessions = sessions

    async def execute(self, token: str) -> None:
        await self._sessions.delete(session_digest(token))


class ResolveSessionUseCase:
    def __init__(self, *, sessions: SessionRepository) -> None:
        self._sessions = sessions

    async def execute(self, token: str) -> ResolvedSession | None:
        digest = session_digest(token)
        now = _now()
        found = await self._sessions.get(digest, now)
        if found is None:
            return None
        # Sliding expiry, written at most once per half-lifetime per browser.
        if found.expires_at - now >= SESSION_LIFETIME / 2:
            return ResolvedSession(session=found)
        expires_at = now + SESSION_LIFETIME
        await self._sessions.extend(digest, expires_at)
        return ResolvedSession(
            session=found, renewed=IssuedSession(token=token, expires_at=expires_at)
        )


class SetupUseCase:
    """Create the first user. Open to anyone until it has run once."""

    def __init__(
        self,
        *,
        users: UserRepository,
        sessions: SessionRepository,
        hasher: PasswordHasher,
        pinned: bool,
    ) -> None:
        self._users = users
        self._sessions = sessions
        self._hasher = hasher
        self._pinned = pinned
        self._lock = asyncio.Lock()

    async def execute(self, username: str, password: str) -> IssuedSession:
        if self._pinned:
            raise AuthLockedError(_LOCKED)
        name = _checked(username, password)
        async with self._lock:
            if await self._users.first() is not None:
                raise AlreadySetUpError
            hashed = await asyncio.to_thread(self._hasher.hash, password)
            user = await self._users.save(name, hashed)
        log.info("first user created", username=user.username)
        return await _issue(self._sessions, user.id)


class ChangeCredentialsUseCase:
    def __init__(
        self,
        *,
        users: UserRepository,
        sessions: SessionRepository,
        hasher: PasswordHasher,
        pinned: bool,
    ) -> None:
        self._users = users
        self._sessions = sessions
        self._hasher = hasher
        self._pinned = pinned

    async def execute(
        self,
        *,
        current_password: str,
        username: str,
        password: str,
        keep_token: str | None,
    ) -> UserRecord:
        if self._pinned:
            raise AuthLockedError(_LOCKED)
        user = await self._users.first()
        if user is None or not await asyncio.to_thread(
            self._hasher.verify, current_password, user.password_hash
        ):
            raise InvalidCredentialsError
        name = _checked(username, password)
        hashed = await asyncio.to_thread(self._hasher.hash, password)
        saved = await self._users.save(name, hashed)
        keep = session_digest(keep_token) if keep_token else None
        await self._sessions.delete_for_user(saved.id, keep=keep)
        log.info("credentials changed; other sessions signed out", username=saved.username)
        return saved


class SyncEnvCredentialsUseCase:
    """Make the stored user match MUXARR_USERNAME/MUXARR_PASSWORD.

    Rewritten on every start, which is also how a forgotten password is reset.
    """

    def __init__(
        self, *, users: UserRepository, sessions: SessionRepository, hasher: PasswordHasher
    ) -> None:
        self._users = users
        self._sessions = sessions
        self._hasher = hasher

    async def execute(self, username: str, password: str) -> None:
        user = await self._users.first()
        if (
            user is not None
            and user.username == username
            and not self._hasher.needs_rehash(user.password_hash)
            and await asyncio.to_thread(self._hasher.verify, password, user.password_hash)
        ):
            return
        hashed = await asyncio.to_thread(self._hasher.hash, password)
        saved = await self._users.save(username, hashed)
        await self._sessions.delete_for_user(saved.id)
        log.info("login set from the environment", username=username)


@dataclass(frozen=True, slots=True)
class AuthStatus:
    setup_required: bool
    username: str | None


class GetAuthStatusUseCase:
    def __init__(self, *, users: UserRepository) -> None:
        self._users = users

    async def execute(self, method: AuthMethod) -> AuthStatus:
        user = await self._users.first()
        return AuthStatus(
            # A proxy in front does the signing in, so there is nobody to create.
            setup_required=user is None and method == "forms",
            username=user.username if user else None,
        )
