"""Persisted settings overrides."""

from __future__ import annotations

from src.db.session import DBManager
from src.infrastructure.settings.repository import SqlAlchemySettingsRepository


async def test_an_empty_store_reads_as_revision_zero(db: DBManager) -> None:
    snapshot = await SqlAlchemySettingsRepository(db).load()

    assert snapshot.revision == 0
    assert snapshot.overrides == {}


async def test_a_save_is_read_back(db: DBManager) -> None:
    store = SqlAlchemySettingsRepository(db)

    await store.save({"dedupe": "off"})

    assert (await store.load()).overrides == {"dedupe": "off"}


async def test_each_save_bumps_the_revision(db: DBManager) -> None:
    """The worker notices a change by this integer alone."""
    store = SqlAlchemySettingsRepository(db)

    first = await store.save({"dedupe": "off"})
    second = await store.save({"dedupe": "language"})

    assert second.revision > first.revision
    assert await store.revision() == second.revision


async def test_a_save_replaces_the_whole_payload(db: DBManager) -> None:
    store = SqlAlchemySettingsRepository(db)

    await store.save({"dedupe": "off", "ai_model": "tiny"})
    await store.save({"dedupe": "language"})

    assert (await store.load()).overrides == {"dedupe": "language"}
