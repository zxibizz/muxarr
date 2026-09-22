"""Read the stored overrides.

The caller layers these over its own environment-derived settings; this use
case deliberately knows nothing about ``Settings`` so it stays a thin read.
"""

from __future__ import annotations

from src.application.interfaces.settings import SettingsRepository, SettingsSnapshot


class GetSettingsUseCase:
    def __init__(self, *, store: SettingsRepository) -> None:
        self._store = store

    async def execute(self) -> SettingsSnapshot:
        return await self._store.load()
