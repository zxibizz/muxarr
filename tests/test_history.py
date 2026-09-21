from __future__ import annotations

import pytest

from muxarr.history import HistoryStore


@pytest.fixture
def store() -> HistoryStore:
    return HistoryStore()


def add(store: HistoryStore, **overrides: object) -> int:
    payload: dict[str, object] = {
        "app": "radarr",
        "title": "Movie.2024-GRP.mkv",
        "move_status": "RenameRequested",
        "reason": "embedded 1 external track(s)",
        "source_path": "/downloads/Movie.2024-GRP/Movie.2024-GRP.mkv",
        "destination_path": "/library/Movie (2024)/Movie (2024).mkv",
    }
    payload.update(overrides)
    return store.record(**payload)  # type: ignore[arg-type]


def test_record_returns_an_id(store: HistoryStore) -> None:
    assert add(store) > 0


def test_round_trip(store: HistoryStore) -> None:
    operation_id = add(
        store,
        added_tracks=["subtitles:Russian"],
        rejected_tracks=[{"track": "eng.srt", "reason": "already present in container"}],
        episodes=[2, 3],
        season=1,
        duration_ms=1234,
        source_bytes=100,
        output_bytes=120,
    )

    found = store.get(operation_id)

    assert found is not None
    assert found.added_tracks == ["subtitles:Russian"]
    assert found.rejected_tracks == [
        {"track": "eng.srt", "reason": "already present in container"}
    ]
    assert found.episodes == [2, 3]
    assert found.season == 1
    assert found.duration_ms == 1234
    assert found.muxed is True


def test_get_unknown_id_returns_none(store: HistoryStore) -> None:
    assert store.get(999) is None


def test_empty_episodes_round_trip_as_empty_list(store: HistoryStore) -> None:
    found = store.get(add(store))

    assert found is not None
    assert found.episodes == []


def test_deferred_is_not_muxed(store: HistoryStore) -> None:
    found = store.get(add(store, move_status="DeferMove", reason="no external tracks"))

    assert found is not None
    assert found.muxed is False


class TestListing:
    def test_newest_first(self, store: HistoryStore) -> None:
        add(store, title="first.mkv")
        add(store, title="second.mkv")

        page = store.list()

        assert [op.title for op in page.items] == ["second.mkv", "first.mkv"]

    def test_pagination(self, store: HistoryStore) -> None:
        for index in range(5):
            add(store, title=f"{index}.mkv")

        page = store.list(limit=2, offset=2)

        assert page.total == 5
        assert len(page.items) == 2
        assert page.offset == 2

    def test_limit_is_clamped(self, store: HistoryStore) -> None:
        assert store.list(limit=100_000).limit == 500
        assert store.list(limit=0).limit == 1

    def test_negative_offset_is_clamped(self, store: HistoryStore) -> None:
        assert store.list(offset=-10).offset == 0

    def test_filter_by_status(self, store: HistoryStore) -> None:
        add(store, move_status="RenameRequested")
        add(store, move_status="DeferMove")

        page = store.list(status="DeferMove")

        assert page.total == 1
        assert page.items[0].move_status == "DeferMove"

    def test_filter_by_app(self, store: HistoryStore) -> None:
        add(store, app="radarr")
        add(store, app="sonarr")

        assert store.list(app="sonarr").total == 1

    def test_search_matches_title_path_and_reason(self, store: HistoryStore) -> None:
        add(store, title="Hanaori.mkv")
        add(store, source_path="/downloads/Надписи/x.mkv")
        add(store, reason="mux failed, leaving the import to *arr")

        assert store.list(query="Hanaori").total == 1
        assert store.list(query="Надписи").total == 1
        assert store.list(query="mux failed").total == 1

    def test_filters_combine(self, store: HistoryStore) -> None:
        add(store, app="sonarr", move_status="DeferMove")
        add(store, app="sonarr", move_status="RenameRequested")
        add(store, app="radarr", move_status="DeferMove")

        assert store.list(app="sonarr", status="DeferMove").total == 1

    def test_search_wildcards_are_not_injected(self, store: HistoryStore) -> None:
        """A literal % or _ must not behave as a LIKE wildcard."""
        add(store, title="plain.mkv")

        assert store.list(query="%").total == 0
        assert store.list(query="_").total == 0

    def test_search_finds_literal_wildcard_characters(self, store: HistoryStore) -> None:
        add(store, title="100% complete.mkv")

        assert store.list(query="100%").total == 1


class TestStats:
    def test_empty(self, store: HistoryStore) -> None:
        stats = store.stats()

        assert (stats.total, stats.muxed, stats.deferred, stats.tracks_added) == (0, 0, 0, 0)

    def test_counts_and_tracks(self, store: HistoryStore) -> None:
        add(store, added_tracks=["a", "b"])
        add(store, added_tracks=["c"])
        add(store, move_status="DeferMove")

        stats = store.stats()

        assert stats.total == 3
        assert stats.muxed == 2
        assert stats.deferred == 1
        assert stats.tracks_added == 3

    def test_recent_window_counts_fresh_rows(self, store: HistoryStore) -> None:
        add(store)

        assert store.stats().last_24h == 1


class TestMaintenance:
    def test_clear(self, store: HistoryStore) -> None:
        add(store)
        add(store)

        assert store.clear() == 2
        assert store.list().total == 0
