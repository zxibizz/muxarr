"""Shared JSON decoding for the probe adapters."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.domain.errors import ProbeError


def load_json_object(path: Path, payload: str) -> dict[str, Any]:
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ProbeError(f"probe output for {path} was not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ProbeError(f"probe output for {path} was not a JSON object")
    return parsed
