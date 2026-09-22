"""Settings reaching the worker process without a restart.

The API and the worker share nothing but the database, so a change made in the
browser is only real once the worker has acted on it.
"""

from __future__ import annotations

from pathlib import Path

from src.core.container import AppContainer
from src.db.session import DBManager
from src.infrastructure.history.repository import SqlAlchemyHistoryRepository
from src.infrastructure.jobs.repository import SqlAlchemyJobRepository
from src.infrastructure.jobs.worker_state import SqlAlchemyWorkerStateRepository
from src.infrastructure.settings.repository import SqlAlchemySettingsRepository
from src.settings.config import Settings


def build(db: DBManager, **kwargs: object) -> AppContainer:
    settings = Settings(read_roots=(Path("/downloads"),), db_url="sqlite+aiosqlite:///:memory:")
    return AppContainer(
        settings,
        history=SqlAlchemyHistoryRepository(db),
        jobs=SqlAlchemyJobRepository(db),
        worker_state=SqlAlchemyWorkerStateRepository(db),
        settings_store=SqlAlchemySettingsRepository(db),
        env={},
        **kwargs,  # type: ignore[arg-type]
    )


async def test_a_stored_override_is_picked_up(db: DBManager) -> None:
    container = build(db)
    await SqlAlchemySettingsRepository(db).save({"dedupe": "off"})

    assert await container.sync_settings() is True
    assert container.settings.dedupe == "off"


async def test_an_unchanged_revision_is_a_no_op(db: DBManager) -> None:
    container = build(db)
    await SqlAlchemySettingsRepository(db).save({"dedupe": "off"})

    await container.sync_settings()

    assert await container.sync_settings() is False


async def test_derived_objects_are_rebuilt(db: DBManager) -> None:
    """A cached use case would otherwise keep acting on the old settings."""
    container = build(db)
    before = container.handle_import
    await SqlAlchemySettingsRepository(db).save({"max_external_tracks": 2})

    await container.sync_settings()

    assert container.handle_import is not before
    assert container.handle_import._settings.max_external_tracks == 2


async def test_the_engine_survives_a_reload(db: DBManager) -> None:
    """Disposing it would drop the in-flight queue along with it."""
    container = build(db)
    before = container.jobs
    await SqlAlchemySettingsRepository(db).save({"dedupe": "off"})

    await container.sync_settings()

    assert container.jobs is before


async def test_a_locked_field_is_ignored_on_reload(db: DBManager) -> None:
    settings = Settings(read_roots=(Path("/downloads"),))
    container = AppContainer(
        settings,
        history=SqlAlchemyHistoryRepository(db),
        jobs=SqlAlchemyJobRepository(db),
        worker_state=SqlAlchemyWorkerStateRepository(db),
        settings_store=SqlAlchemySettingsRepository(db),
        env={"MUXARR_DEDUPE": "language"},
    )
    # A row written before the variable was added to compose.
    await SqlAlchemySettingsRepository(db).save({"dedupe": "off"})

    await container.sync_settings()

    assert container.settings.dedupe == settings.dedupe


async def test_an_unusable_payload_keeps_the_current_settings(db: DBManager) -> None:
    container = build(db)
    await SqlAlchemySettingsRepository(db).save({"dedupe": "nonsense"})

    assert await container.sync_settings() is False
    assert container.settings.dedupe == "language_codec"
