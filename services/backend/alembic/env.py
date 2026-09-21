"""Alembic environment.

Migrations run synchronously: the async driver in ``MUXARR_DB_URL`` is swapped
for its blocking counterpart so alembic's own engine handling applies unchanged.
"""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.db import metadata  # noqa: E402
from src.domain import models  # noqa: E402,F401  (import registers the tables)
from src.settings.config import DEFAULT_DB_URL  # noqa: E402

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = metadata

_ASYNC_TO_SYNC = {
    "sqlite+aiosqlite": "sqlite",
    "postgresql+asyncpg": "postgresql+psycopg",
}


def _database_url() -> str:
    url = os.environ.get("MUXARR_DB_URL", "").strip() or DEFAULT_DB_URL
    for async_driver, sync_driver in _ASYNC_TO_SYNC.items():
        if url.startswith(f"{async_driver}:"):
            return sync_driver + url[len(async_driver) :]
    return url


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _database_url()
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # SQLite cannot ALTER most things in place.
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
