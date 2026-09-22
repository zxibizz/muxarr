"""Persist a change to the UI-editable settings.

The merged result is coerced before it is stored, so a payload that would make
the daemon unusable is rejected at the boundary rather than at the next reload.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from src.application.interfaces.settings import SettingsRepository, SettingsSnapshot
from src.settings.config import ConfigError, Settings
from src.settings.mutable import BY_NAME, apply_overrides, reject_locked


class UpdateSettingsUseCase:
    def __init__(
        self,
        *,
        store: SettingsRepository,
        locked: frozenset[str],
        base: Callable[[], Settings],
    ) -> None:
        self._store = store
        self._locked = locked
        self._base = base

    async def execute(self, changes: Mapping[str, str]) -> SettingsSnapshot:
        unknown = sorted(set(changes) - set(BY_NAME))
        if unknown:
            raise ConfigError(f"not an editable setting: {', '.join(unknown)}")
        reject_locked(changes, self._locked)

        stored = await self._store.load()
        merged = {**stored.overrides, **changes}
        apply_overrides(self._base(), merged, locked=self._locked)
        return await self._store.save(merged)
