"""Contract for the optional LLM backend.

Kept this narrow -- one blocking call in, one string out -- so that swapping the
provider, or stubbing it in a test, never reaches into the discovery logic.
"""

from __future__ import annotations

from typing import Protocol


class ChatCompleter(Protocol):
    def complete(self, *, system: str, user: str, timeout: float) -> str:
        """Return the assistant's raw reply text, or raise ``AiError``."""
        ...
