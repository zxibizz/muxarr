"""The key the shims and scripts present.

Generated once and stored, like the *arr apps' own, unless MUXARR_API_KEY pins it.
"""

from __future__ import annotations

import secrets

from src.application.interfaces.auth import ApiKeyRepository
from src.application.use_cases.auth.exceptions import AuthLockedError
from src.core.logging import get_logger
from src.domain.enums import LogComponent

log = get_logger(LogComponent.USECASE_AUTH)


def new_api_key() -> str:
    return secrets.token_hex(16)


class EnsureApiKeyUseCase:
    def __init__(self, *, store: ApiKeyRepository, pinned: str | None) -> None:
        self._store = store
        self._pinned = pinned

    async def execute(self) -> str:
        if self._pinned is not None:
            return self._pinned
        stored = await self._store.get()
        if stored is not None:
            return stored
        key = await self._store.create_if_absent(new_api_key())
        log.info("generated an API key; copy it from Settings > Security into Radarr/Sonarr")
        return key


class RegenerateApiKeyUseCase:
    def __init__(self, *, store: ApiKeyRepository, pinned: bool) -> None:
        self._store = store
        self._pinned = pinned

    async def execute(self) -> str:
        if self._pinned:
            raise AuthLockedError(
                "the API key is pinned by MUXARR_API_KEY; change it there instead"
            )
        key = new_api_key()
        await self._store.replace(key)
        log.warning("API key regenerated; Radarr/Sonarr need the new one")
        return key
