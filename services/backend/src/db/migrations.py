"""Whether the database schema matches the migrations this build ships."""

from __future__ import annotations

from pathlib import Path

from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine

# services/backend/alembic in a checkout, /app/alembic in the image.
SCRIPT_LOCATION = Path(__file__).resolve().parents[2] / "alembic"


def expected_heads() -> set[str]:
    return set(ScriptDirectory(str(SCRIPT_LOCATION)).get_heads())


async def current_heads(engine: AsyncEngine) -> set[str]:
    async with engine.connect() as connection:
        return await connection.run_sync(_current_heads)


async def schema_is_current(engine: AsyncEngine) -> bool:
    return await current_heads(engine) == expected_heads()


def _current_heads(connection: Connection) -> set[str]:
    return set(MigrationContext.configure(connection).get_current_heads())
