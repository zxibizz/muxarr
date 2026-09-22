"""Probe an AI provider with credentials the user has typed but not saved.

Synchronous, like everything that talks to a completer: the caller runs it on a
thread so the API's event loop keeps serving long-polls.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from src.application.interfaces.ai import ChatCompleterFactory
from src.domain.errors import AiError

# The user is watching a spinner. Also the ceiling on how long an unauthenticated
# -- to the provider -- request from this process can be held open.
MAX_TIMEOUT = 10.0

# Providers echo request fragments in error bodies; keep only a usable hint.
MAX_MESSAGE_CHARS = 300

_SYSTEM = 'You are a connectivity probe. Reply with exactly {"ok": true} and nothing else.'
_USER = "ping"


@dataclass(frozen=True, slots=True)
class AiProbe:
    base_url: str
    model: str
    api_key: str | None
    timeout: float


@dataclass(frozen=True, slots=True)
class AiProbeResult:
    ok: bool
    message: str
    latency_ms: int


class TestAiProviderUseCase:
    def __init__(self, *, completers: ChatCompleterFactory) -> None:
        self._completers = completers

    def execute(self, probe: AiProbe) -> AiProbeResult:
        completer = self._completers.create(
            base_url=probe.base_url, model=probe.model, api_key=probe.api_key
        )
        started = time.monotonic()
        try:
            completer.complete(
                system=_SYSTEM, user=_USER, timeout=min(probe.timeout, MAX_TIMEOUT)
            )
        except AiError as exc:
            return AiProbeResult(
                ok=False,
                message=str(exc)[:MAX_MESSAGE_CHARS],
                latency_ms=_elapsed(started),
            )
        return AiProbeResult(
            ok=True, message=f"{probe.model} replied", latency_ms=_elapsed(started)
        )


def _elapsed(started: float) -> int:
    return int((time.monotonic() - started) * 1000)
