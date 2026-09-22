"""Client for any OpenAI-compatible ``/chat/completions`` endpoint.

Deliberately not a vendor SDK: the same three settings point at OpenAI,
OpenRouter, Groq or a local Ollama/LM Studio instance, which is the only way a
self-hoster can keep their filenames on their own machine.

Synchronous on purpose. The import pipeline is synchronous and already runs on a
worker thread, so an async client would buy nothing and need an event loop.

This is muxarr's only outbound HTTP. Every failure becomes :class:`AiError`, which
the caller degrades from rather than propagates.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from src.core.logging import get_logger
from src.domain.enums import LogComponent
from src.domain.errors import AiError

log = get_logger(LogComponent.INFRA_AI)

# A well-formed answer is a few hundred bytes of JSON; anything near this is junk
# and parsing it would only waste the worker's time.
MAX_REPLY_CHARS = 64 * 1024

# Providers echo the offending request in an error body; keep only a hint of it.
MAX_ERROR_CHARS = 200


class _ResponseFormatError(Exception):
    """The provider rejected ``response_format``; worth one retry without it."""


class OpenAICompatibleChatCompleter:
    """Adapter object for the container; implements ``ChatCompleter``."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._url = f"{base_url.rstrip('/')}/chat/completions"
        self._model = model
        self._api_key = api_key
        self._transport = transport

    def complete(self, *, system: str, user: str, timeout: float) -> str:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            # The task is extraction, not writing; sampling only invents tracks.
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }

        started = time.monotonic()
        try:
            data = self._post(payload, timeout=timeout)
        except _ResponseFormatError:
            log.debug("provider rejected response_format, retrying without it", model=self._model)
            payload.pop("response_format")
            data = self._post(payload, timeout=timeout)

        content = _content(data)
        usage = data.get("usage")
        log.info(
            "ai completion",
            model=self._model,
            latency_ms=int((time.monotonic() - started) * 1000),
            prompt_tokens=usage.get("prompt_tokens") if isinstance(usage, dict) else None,
            completion_tokens=usage.get("completion_tokens") if isinstance(usage, dict) else None,
        )
        return content

    def _post(self, payload: dict[str, Any], *, timeout: float) -> dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        try:
            with httpx.Client(
                timeout=timeout,
                transport=self._transport,
                # The base URL is operator-supplied; a redirect would let a
                # provider bounce this request at an address we never vetted.
                follow_redirects=False,
            ) as client:
                response = client.post(self._url, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise AiError(f"could not reach {self._url}: {exc}") from exc

        if response.status_code == httpx.codes.BAD_REQUEST and "response_format" in payload:
            raise _ResponseFormatError
        if response.status_code != httpx.codes.OK:
            raise AiError(
                f"{self._url} returned HTTP {response.status_code}: "
                f"{response.text[:MAX_ERROR_CHARS]}"
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise AiError(f"{self._url} did not return JSON") from exc
        if not isinstance(data, dict):
            raise AiError(f"{self._url} returned {type(data).__name__}, expected an object")
        return data


class OpenAICompatibleCompleterFactory:
    """Builds completers for credentials the container has not been given.

    The settings page tests what the user has typed, which is by definition not
    the configuration the container was wired with.
    """

    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        self._transport = transport

    def create(
        self, *, base_url: str, model: str, api_key: str | None
    ) -> OpenAICompatibleChatCompleter:
        return OpenAICompatibleChatCompleter(
            base_url=base_url, model=model, api_key=api_key, transport=self._transport
        )


def _content(data: dict[str, Any]) -> str:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise AiError("provider returned no choices")

    first = choices[0]
    message = first.get("message") if isinstance(first, dict) else None
    content = message.get("content") if isinstance(message, dict) else None

    if not isinstance(content, str) or not content.strip():
        raise AiError("provider returned an empty completion")
    if len(content) > MAX_REPLY_CHARS:
        raise AiError(f"provider returned {len(content)} characters, over the reply limit")
    return content
