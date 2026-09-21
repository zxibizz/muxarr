"""Raised by the history use cases."""

from __future__ import annotations

from src.domain.errors import MuxarrError


class OperationNotFoundError(MuxarrError):
    def __init__(self, operation_id: int) -> None:
        super().__init__(f"operation {operation_id} not found")
        self.operation_id = operation_id
