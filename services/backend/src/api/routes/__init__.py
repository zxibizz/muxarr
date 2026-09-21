"""Router registration."""

from __future__ import annotations

from fastapi import FastAPI

from src.api.routes import health, history, imports


def register_routes(app: FastAPI) -> None:
    app.include_router(health.router)
    app.include_router(history.router)
    app.include_router(imports.router)
