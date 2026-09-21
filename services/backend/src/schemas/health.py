"""Health wire model."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class Health(BaseModel):
    status: Literal["ok"] = "ok"
    version: str
    read_roots: list[str]
    auth_required: bool = False
