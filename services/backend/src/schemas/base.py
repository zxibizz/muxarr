"""Base for response bodies."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class WireModel(BaseModel):
    # A defaulted field is still always sent, so the generated client must not mark it optional.
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)
