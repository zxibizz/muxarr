"""Domain exception -> HTTP status.

Route handlers never catch these; the handler registered by the app factory
turns them into responses so the mapping lives in one place.
"""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from src.application.interfaces.jobs import JobConflictError
from src.application.use_cases.history.exceptions import OperationNotFoundError
from src.domain.errors import MuxarrError
from src.settings.config import ConfigError
from src.settings.mutable import SettingsLockedError

DOMAIN_ERROR_MAP: dict[type[MuxarrError], int] = {
    OperationNotFoundError: status.HTTP_404_NOT_FOUND,
    JobConflictError: status.HTTP_409_CONFLICT,
    SettingsLockedError: status.HTTP_409_CONFLICT,
    ConfigError: status.HTTP_422_UNPROCESSABLE_CONTENT,
}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(MuxarrError)
    async def _handle(_: Request, exc: MuxarrError) -> JSONResponse:
        code = DOMAIN_ERROR_MAP.get(type(exc), status.HTTP_500_INTERNAL_SERVER_ERROR)
        return JSONResponse(status_code=code, content={"detail": str(exc)})
