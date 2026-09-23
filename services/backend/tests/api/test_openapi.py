from __future__ import annotations

import json
from pathlib import Path

from src.api.app import create_app
from src.settings.config import Settings

COMMITTED = Path(__file__).resolve().parents[4] / "services" / "frontend" / "openapi.json"


def test_the_frontend_schema_is_current() -> None:
    """The UI's types are generated from this file; regenerate with `make gen-api`."""
    live = create_app(Settings(read_roots=(Path("/"),))).openapi()

    assert json.loads(COMMITTED.read_text(encoding="utf-8")) == live
