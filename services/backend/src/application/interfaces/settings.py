"""Contract for the persisted settings overrides.

``revision`` exists so the worker process can notice a change with one cheap
integer read instead of re-parsing the payload on every poll.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True, slots=True)
class SettingsSnapshot:
    revision: int
    overrides: Mapping[str, str] = field(default_factory=dict)


class SettingsRepository(Protocol):
    async def load(self) -> SettingsSnapshot:
        """Return the stored overrides, or an empty snapshot if none exist."""
        ...

    async def save(self, overrides: Mapping[str, str]) -> SettingsSnapshot:
        """Replace the stored overrides and bump the revision."""
        ...

    async def revision(self) -> int:
        """Return the current revision without reading the payload."""
        ...
