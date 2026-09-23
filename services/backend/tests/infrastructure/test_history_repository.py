from __future__ import annotations

from src.application.interfaces.history import NewOperation
from src.db.session import DBManager
from src.domain.journal import LogEntry, RejectedTrack, RemovedTrack, TrackDetail
from src.domain.models import Operation
from src.infrastructure.history.repository import SqlAlchemyHistoryRepository

Store = SqlAlchemyHistoryRepository


def a_track(**overrides: object) -> TrackDetail:
    payload: dict[str, object] = {"kind": "subtitles", "label": "Russian", "language": "rus"}
    payload.update(overrides)
    return TrackDetail(**payload)  # type: ignore[arg-type]


async def add(store: Store, **overrides: object) -> int:
    payload: dict[str, object] = {
        "app": "radarr",
        "title": "Movie.2024-GRP.mkv",
        "move_status": "RenameRequested",
        "reason": "embedded 1 external track(s)",
        "source_path": "/downloads/Movie.2024-GRP/Movie.2024-GRP.mkv",
        "destination_path": "/library/Movie (2024)/Movie (2024).mkv",
    }
    payload.update(overrides)
    return await store.record(NewOperation(**payload))  # type: ignore[arg-type]


async def test_record_returns_an_id(history: Store) -> None:
    assert await add(history) > 0


async def test_round_trip(history: Store) -> None:
    operation_id = await add(
        history,
        added_tracks=[a_track(file="rus.srt", source="ai")],
        rejected_tracks=[
            RejectedTrack(track="eng.srt", reason="already present in container", language="eng")
        ],
        removed_tracks=[
            RemovedTrack(index=2, kind="audio", language="fre", name="French", forced=True)
        ],
        log=[
            LogEntry(
                ts="2026-01-01T00:00:00Z",
                level="INFO",
                component="usecase.import",
                message="embedding subtitles",
                stage="selection",
                context={"file": "rus.srt"},
            )
        ],
        episodes=[2, 3],
        season=1,
        duration_ms=1234,
        source_bytes=100,
        output_bytes=120,
    )

    found = await history.get(operation_id)

    assert found is not None
    assert found.added_tracks == [a_track(file="rus.srt", source="ai")]
    assert found.rejected_tracks == [
        RejectedTrack(track="eng.srt", reason="already present in container", language="eng")
    ]
    assert found.removed_tracks == [
        RemovedTrack(index=2, kind="audio", language="fre", name="French", forced=True)
    ]
    assert [(e.stage, e.message, e.context) for e in found.log] == [
        ("selection", "embedding subtitles", {"file": "rus.srt"})
    ]
    assert found.episodes == [2, 3]
    assert found.season == 1
    assert found.duration_ms == 1234
    assert found.muxed is True


async def test_tracks_stored_before_they_were_structured_still_read_back(
    db: DBManager, history: Store
) -> None:
    """Rows written by an older muxarr hold a display string, not an object."""
    operation_id = await add(history)
    async with db.session() as session:
        row = await session.get(Operation, operation_id)
        assert row is not None
        row.added_tracks = '["audio:Russian [ai]"]'
        await session.commit()

    found = await history.get(operation_id)

    assert found is not None
    assert found.added_tracks == [TrackDetail(kind="audio", label="Russian", source="ai")]
    assert found.log == []


async def test_get_unknown_id_returns_none(history: Store) -> None:
    assert await history.get(999) is None


async def test_byte_counts_past_32_bits_round_trip(history: Store) -> None:
    size = 60 * 1024**3
    found = await history.get(await add(history, source_bytes=size, output_bytes=size + 1))

    assert found is not None
    assert (found.source_bytes, found.output_bytes) == (size, size + 1)


async def test_empty_episodes_round_trip_as_empty_list(history: Store) -> None:
    found = await history.get(await add(history))

    assert found is not None
    assert found.episodes == []


async def test_deferred_is_not_muxed(history: Store) -> None:
    found = await history.get(
        await add(history, move_status="DeferMove", reason="no external tracks")
    )

    assert found is not None
    assert found.muxed is False


class TestListing:
    async def test_newest_first(self, history: Store) -> None:
        await add(history, title="first.mkv")
        await add(history, title="second.mkv")

        page = await history.list()

        assert [op.title for op in page.items] == ["second.mkv", "first.mkv"]

    async def test_pagination(self, history: Store) -> None:
        for index in range(5):
            await add(history, title=f"{index}.mkv")

        page = await history.list(limit=2, offset=2)

        assert page.total == 5
        assert len(page.items) == 2
        assert page.offset == 2

    async def test_limit_is_clamped(self, history: Store) -> None:
        assert (await history.list(limit=100_000)).limit == 500
        assert (await history.list(limit=0)).limit == 1

    async def test_negative_offset_is_clamped(self, history: Store) -> None:
        assert (await history.list(offset=-10)).offset == 0

    async def test_filter_by_status(self, history: Store) -> None:
        await add(history, move_status="RenameRequested")
        await add(history, move_status="DeferMove")

        page = await history.list(status="DeferMove")

        assert page.total == 1
        assert page.items[0].move_status == "DeferMove"

    async def test_filter_by_app(self, history: Store) -> None:
        await add(history, app="radarr")
        await add(history, app="sonarr")

        assert (await history.list(app="sonarr")).total == 1

    async def test_search_matches_title_path_and_reason(self, history: Store) -> None:
        await add(history, title="Hanaori.mkv")
        await add(history, source_path="/downloads/Надписи/x.mkv")
        await add(history, reason="mux failed, leaving the import to *arr")

        assert (await history.list(query="Hanaori")).total == 1
        assert (await history.list(query="Надписи")).total == 1
        assert (await history.list(query="mux failed")).total == 1

    async def test_search_ignores_ascii_case(self, history: Store) -> None:
        await add(history, title="Hanaori.mkv")

        assert (await history.list(query="hANAORI")).total == 1

    async def test_filters_combine(self, history: Store) -> None:
        await add(history, app="sonarr", move_status="DeferMove")
        await add(history, app="sonarr", move_status="RenameRequested")
        await add(history, app="radarr", move_status="DeferMove")

        assert (await history.list(app="sonarr", status="DeferMove")).total == 1

    async def test_search_wildcards_are_not_injected(self, history: Store) -> None:
        """A literal % or _ must not behave as a LIKE wildcard."""
        await add(history, title="plain.mkv")

        assert (await history.list(query="%")).total == 0
        assert (await history.list(query="_")).total == 0

    async def test_search_finds_literal_wildcard_characters(self, history: Store) -> None:
        await add(history, title="100% complete.mkv")

        assert (await history.list(query="100%")).total == 1


class TestStats:
    async def test_empty(self, history: Store) -> None:
        stats = await history.stats()

        assert (stats.total, stats.muxed, stats.deferred, stats.tracks_added) == (0, 0, 0, 0)

    async def test_counts_and_tracks(self, history: Store) -> None:
        await add(history, added_tracks=[a_track(), a_track(label="English")])
        await add(history, added_tracks=[a_track()])
        await add(history, move_status="DeferMove")

        stats = await history.stats()

        assert stats.total == 3
        assert stats.muxed == 2
        assert stats.deferred == 1
        assert stats.tracks_added == 3

    async def test_recent_window_counts_fresh_rows(self, history: Store) -> None:
        await add(history)

        assert (await history.stats()).last_24h == 1


class TestMaintenance:
    async def test_clear(self, history: Store) -> None:
        await add(history)
        await add(history)

        assert await history.clear() == 2
        assert (await history.list()).total == 0

    async def test_prune_keeps_the_newest_records(self, history: Store) -> None:
        for index in range(5):
            await add(history, title=f"{index}.mkv")

        assert await history.prune(2) == 3
        assert [op.title for op in (await history.list()).items] == ["4.mkv", "3.mkv"]

    async def test_prune_below_the_cap_removes_nothing(self, history: Store) -> None:
        await add(history)

        assert await history.prune(200) == 0
        assert (await history.list()).total == 1

    async def test_prune_of_an_empty_history_is_a_no_op(self, history: Store) -> None:
        assert await history.prune(200) == 0
