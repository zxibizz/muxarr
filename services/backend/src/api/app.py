"""HTTP daemon.

Runs in its own container alongside Radarr/Sonarr, owning the ffmpeg/mkvtoolnix
dependency so the *arr container needs nothing but a shell.

Keeping the mux out-of-process also means stray mkvmerge output can never reach
the shim's stdout, where *arr would try to parse it as protocol.

Imports are asynchronous: the shim submits a job and long-polls for the outcome.
Holding one request open for the length of a remux did not survive proxy idle
timeouts, and a dropped reply was indistinguishable from a failed mux.

The built SPA is served by nginx in front of this process, not from here.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src import __version__
from src.api.errors import register_error_handlers
from src.api.routes import register_routes
from src.core.container import AppContainer
from src.core.logging import configure_logging, get_logger
from src.domain.enums import LogComponent
from src.settings.config import Settings

log = get_logger(LogComponent.API)


def create_app(settings: Settings, container: AppContainer | None = None) -> FastAPI:
    resolved = container or AppContainer(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            # The stored overrides only exist once migrations have run; a fresh
            # database is normal, so this must never keep the API from starting.
            await resolved.sync_settings()
        except Exception:
            log.exception("could not load the stored settings; using the environment")
        try:
            yield
        finally:
            await resolved.shutdown()

    app = FastAPI(title="muxarr", version=__version__, lifespan=lifespan)
    app.state.container = resolved
    register_error_handlers(app)
    register_routes(app)
    return app


def build_app() -> FastAPI:
    """ASGI factory for uvicorn: ``uvicorn --factory src.api.app:build_app``.

    A module-level ``app`` would call ``Settings.from_env()`` at import time and
    make every import of this module depend on a configured environment.
    """
    settings = Settings.from_env()
    _start_logging(settings)
    return create_app(settings)


def serve(settings: Settings | None = None) -> None:
    import uvicorn

    resolved = settings or Settings.from_env()
    _start_logging(resolved)
    uvicorn.run(create_app(resolved), host=resolved.host, port=resolved.port)


def _start_logging(settings: Settings) -> None:
    configure_logging(level=settings.log_level, serialize=settings.log_json)
    if settings.auth_token is None:
        log.warning(
            "MUXARR_TOKEN is not set; the API is unauthenticated. Bind to a private network only."
        )
