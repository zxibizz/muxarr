"""Declarative base. Alembic autogenerate reads :data:`metadata`."""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


metadata = Base.metadata
