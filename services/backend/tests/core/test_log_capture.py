from __future__ import annotations

import asyncio

from src.core.logging import capture_log, get_logger
from src.domain.enums import LogComponent

log = get_logger(LogComponent.USECASE_IMPORT)


def test_records_inside_the_scope_are_captured() -> None:
    with capture_log(10) as entries:
        log.bind(stage="selection", file="rus.srt").info("embedding subtitles Russian")

    assert [(e.level, e.message, e.stage, e.component) for e in entries] == [
        ("INFO", "embedding subtitles Russian", "selection", "usecase.import")
    ]
    assert entries[0].context == {"file": "rus.srt"}


def test_nothing_is_captured_once_the_scope_closes() -> None:
    with capture_log(10) as entries:
        log.info("inside")
    log.info("outside")

    assert [e.message for e in entries] == ["inside"]


def test_a_limit_of_zero_disables_the_capture() -> None:
    with capture_log(0) as entries:
        log.info("inside")

    assert entries == []


def test_the_tail_is_dropped_with_a_marker_once_the_limit_is_reached() -> None:
    with capture_log(3) as entries:
        for index in range(10):
            log.info(f"line {index}")

    assert [e.message for e in entries] == ["line 0", "line 1", "log truncated after 3 entries"]


async def test_concurrent_imports_do_not_see_each_others_records() -> None:
    """Each task copies the context, so the sink can filter on buffer identity."""

    async def run(name: str) -> list[str]:
        with capture_log(10) as entries:
            log.info(f"{name} started")
            await asyncio.sleep(0)
            log.info(f"{name} finished")
            return [e.message for e in entries]

    first, second = await asyncio.gather(run("a"), run("b"))

    assert first == ["a started", "a finished"]
    assert second == ["b started", "b finished"]
