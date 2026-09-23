"""Async engine and session factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


class DBManager:
    def __init__(self, url: str, *, echo: bool = False) -> None:
        # The worker lives for weeks; without a ping a database restart would fail
        # the first query on every pooled connection.
        self._engine: AsyncEngine = create_async_engine(
            url, echo=echo, future=True, pool_pre_ping=True
        )
        self._sessions = async_sessionmaker(self._engine, expire_on_commit=False)

    @property
    def engine(self) -> AsyncEngine:
        return self._engine

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self._sessions() as session:
            yield session

    async def dispose(self) -> None:
        await self._engine.dispose()
