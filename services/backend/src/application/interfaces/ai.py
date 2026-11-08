"""Contract for the optional LLM backend.

Kept this narrow -- one blocking call in, one string out -- so that swapping the
provider, or stubbing it in a test, never reaches into the discovery logic.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class ReplySchema:
    """The JSON Schema a reply must follow, for providers that can enforce one."""

    name: str
    schema: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class RejectedReply:
    """A reply that could not be used, handed back so the model can correct it.

    Asking the same question again at temperature 0 gets the same broken answer;
    showing the model its own reply and what was wrong with it does not.
    """

    reply: str
    problem: str


class ChatCompleter(Protocol):
    def complete(
        self,
        *,
        system: str,
        user: str,
        timeout: float,
        schema: ReplySchema | None = None,
        rejected: RejectedReply | None = None,
    ) -> str:
        """Return the assistant's raw reply text, or raise ``AiError``."""
        ...


class ChatCompleterFactory(Protocol):
    def create(self, *, base_url: str, model: str, api_key: str | None) -> ChatCompleter:
        """Build a completer for credentials that may not be the saved ones."""
        ...
