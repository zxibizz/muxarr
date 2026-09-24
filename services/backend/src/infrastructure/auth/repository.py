"""Users, sessions and the stored API key."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import CursorResult, delete, func, select, update
from sqlalchemy.exc import IntegrityError

from src.application.interfaces.auth import SessionRecord, UserRecord
from src.db.session import DBManager
from src.domain.models import AuthConfig, LoginSession, User

_ROW_ID = 1


class SqlAlchemyUserRepository:
    def __init__(self, db: DBManager) -> None:
        self._db = db

    async def first(self) -> UserRecord | None:
        async with self._db.session() as session:
            row = await session.scalar(select(User).order_by(User.id).limit(1))
            return _user(row) if row is not None else None

    async def find(self, username: str) -> UserRecord | None:
        async with self._db.session() as session:
            row = await session.scalar(
                select(User).where(func.lower(User.username) == username.strip().lower())
            )
            return _user(row) if row is not None else None

    async def save(self, username: str, password_hash: str) -> UserRecord:
        now = _iso(datetime.now(UTC))
        async with self._db.session() as session:
            row = await session.scalar(select(User).order_by(User.id).limit(1))
            if row is None:
                row = User(
                    username=username, password_hash=password_hash, created_at=now, updated_at=now
                )
                session.add(row)
            else:
                row.username = username
                row.password_hash = password_hash
                row.updated_at = now
            await session.commit()
            return _user(row)


class SqlAlchemySessionRepository:
    def __init__(self, db: DBManager) -> None:
        self._db = db

    async def create(self, digest: str, user_id: int, expires_at: datetime) -> None:
        async with self._db.session() as session:
            session.add(
                LoginSession(
                    id=digest,
                    user_id=user_id,
                    created_at=_iso(datetime.now(UTC)),
                    expires_at=_iso(expires_at),
                )
            )
            await session.commit()

    async def get(self, digest: str, now: datetime) -> SessionRecord | None:
        async with self._db.session() as session:
            row = (
                await session.execute(
                    select(LoginSession.user_id, LoginSession.expires_at, User.username)
                    .join(User, User.id == LoginSession.user_id)
                    .where(LoginSession.id == digest, LoginSession.expires_at > _iso(now))
                )
            ).first()
        if row is None:
            return None
        return SessionRecord(
            user_id=row.user_id,
            username=row.username,
            expires_at=datetime.fromisoformat(row.expires_at),
        )

    async def extend(self, digest: str, expires_at: datetime) -> None:
        async with self._db.session() as session:
            await session.execute(
                update(LoginSession)
                .where(LoginSession.id == digest)
                .values(expires_at=_iso(expires_at))
            )
            await session.commit()

    async def delete(self, digest: str) -> None:
        async with self._db.session() as session:
            await session.execute(delete(LoginSession).where(LoginSession.id == digest))
            await session.commit()

    async def delete_for_user(self, user_id: int, *, keep: str | None = None) -> None:
        statement = delete(LoginSession).where(LoginSession.user_id == user_id)
        if keep is not None:
            statement = statement.where(LoginSession.id != keep)
        async with self._db.session() as session:
            await session.execute(statement)
            await session.commit()

    async def prune(self, now: datetime) -> int:
        async with self._db.session() as session:
            result = cast(
                "CursorResult[Any]",
                await session.execute(
                    delete(LoginSession).where(LoginSession.expires_at <= _iso(now))
                ),
            )
            await session.commit()
            return int(result.rowcount or 0)


class SqlAlchemyApiKeyRepository:
    def __init__(self, db: DBManager) -> None:
        self._db = db

    async def get(self) -> str | None:
        async with self._db.session() as session:
            key = await session.scalar(select(AuthConfig.api_key).where(AuthConfig.id == _ROW_ID))
            return str(key) if key else None

    async def create_if_absent(self, candidate: str) -> str:
        now = _iso(datetime.now(UTC))
        async with self._db.session() as session:
            session.add(AuthConfig(id=_ROW_ID, api_key=candidate, updated_at=now))
            try:
                await session.commit()
            except IntegrityError:
                # Another process won the race; its key is the one to keep.
                await session.rollback()
        stored = await self.get()
        return stored or candidate

    async def replace(self, key: str) -> None:
        now = _iso(datetime.now(UTC))
        async with self._db.session() as session:
            result = cast(
                "CursorResult[Any]",
                await session.execute(
                    update(AuthConfig)
                    .where(AuthConfig.id == _ROW_ID)
                    .values(api_key=key, updated_at=now)
                ),
            )
            if not result.rowcount:
                session.add(AuthConfig(id=_ROW_ID, api_key=key, updated_at=now))
            await session.commit()


def _user(row: User) -> UserRecord:
    return UserRecord(id=row.id, username=row.username, password_hash=row.password_hash)


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
