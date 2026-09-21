"""Central logging configuration using Loguru.

One process, one sink: everything goes to stdout, which is where `docker logs`
and a dev terminal both look. There is no log file and no /logs endpoint, so
nothing here rotates or retains.
"""

from __future__ import annotations

import inspect
import logging
import sys
from typing import TYPE_CHECKING

from loguru import logger

from src.domain.enums import LogComponent

if TYPE_CHECKING:
    from loguru import Logger, Record
else:
    Logger = logger.__class__

# Structured context is invisible under Loguru's default format, so extras are
# rendered explicitly. Markup lives in the template, never in the substituted
# value: Loguru does not parse tags inside record values, and for the same
# reason a path containing braces cannot break the format.
CONSOLE_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
    "<level>{level: <7}</level> | "
    "<cyan>{extra[component]}</cyan> | "
    "<level>{message}</level>"
    "<dim>{extra[context]}</dim>"
)

_RESERVED = ("component", "context")

# These configure their own handlers with propagate=False, so clearing the root
# handler is not enough to capture them -- uvicorn in particular would keep
# printing its own format alongside ours.
_INTERCEPTED = (
    "uvicorn",
    "uvicorn.access",
    "uvicorn.error",
    "fastapi",
    "alembic",
    "sqlalchemy",
    "sqlalchemy.engine",
)


def attach_context(record: Record) -> None:
    """Flatten a record's bound extras into a printable suffix."""
    pairs = " ".join(f"{k}={v}" for k, v in record["extra"].items() if k not in _RESERVED)
    record["extra"]["context"] = f"  {pairs}" if pairs else ""


class InterceptHandler(logging.Handler):
    """Redirect standard logging records to Loguru.

    uvicorn, sqlalchemy and alembic all use stdlib logging; without this their
    output bypasses every sink configured here.
    """

    def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover - thin adapter
        level: int | str
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Without this, every intercepted record is attributed to this handler
        # rather than to the library that logged it.
        frame, depth = inspect.currentframe(), 0
        while frame and (depth == 0 or frame.f_code.co_filename == logging.__file__):
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).bind(
            component=record.name
        ).log(level, record.getMessage())


def _resolve_level(name: str) -> str:
    """Return a level Loguru recognises, falling back to ``INFO``.

    An unusable setting must not take the process down on startup, since logging
    is configured before anything else can report the problem.
    """
    try:
        logger.level(name)
    except ValueError:
        return "INFO"
    return name


def configure_logging(*, level: str = "INFO", serialize: bool = False) -> None:
    """Install the single stdout sink. Takes plain values, not Settings: the CLI
    configures logging before it has any.
    """
    logger.remove()
    logger.configure(
        extra={"component": LogComponent.API.value, "context": ""},
        # Serialised records carry the extras as real fields, so rendering them
        # into a string as well would only duplicate them.
        patcher=None if serialize else attach_context,
    )

    resolved = _resolve_level(level.upper())

    logger.add(
        sys.stdout,
        level=resolved,
        serialize=serialize,
        format="{message}" if serialize else CONSOLE_FORMAT,
        backtrace=False,
        diagnose=False,
    )

    logging.basicConfig(
        handlers=[InterceptHandler()],
        level=getattr(logging, resolved, logging.INFO),
        force=True,
    )

    # Runs after uvicorn's own dictConfig, which is applied before it loads the
    # app factory; hand those records back to the root handler above.
    for name in _INTERCEPTED:
        intercepted = logging.getLogger(name)
        intercepted.handlers = []
        intercepted.propagate = True


def get_logger(component: LogComponent, **extra: object) -> Logger:
    """Return a logger bound to a component.

    ``component`` is required so a module cannot silently log without one; the
    default set by :func:`configure_logging` only covers third-party records
    arriving through the intercept handler.
    """
    return logger.bind(component=component.value, **extra)


__all__ = ["configure_logging", "get_logger", "logger"]
