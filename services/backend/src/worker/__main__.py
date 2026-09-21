"""Entry point: ``python -m src.worker``."""

from __future__ import annotations

import asyncio
import signal

from src.core.container import AppContainer
from src.core.logging import configure_logging, get_logger
from src.domain.enums import LogComponent
from src.settings.config import Settings

log = get_logger(LogComponent.WORKER)


async def run() -> None:
    settings = Settings.from_env()
    configure_logging(level=settings.log_level, serialize=settings.log_json)

    container = AppContainer(settings)
    worker = container.import_worker

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, worker.stop)

    log.info(
        "worker started",
        concurrency=settings.max_concurrent_muxes,
        read_roots=[str(r) for r in settings.read_roots],
    )
    try:
        await worker.run()
    finally:
        await container.shutdown()
    log.info("worker stopped")


def main() -> int:
    asyncio.run(run())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
