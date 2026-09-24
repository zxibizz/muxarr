from __future__ import annotations

import pytest

from src.domain.arr import ArrContext, item_url
from src.schemas.arr import ArrPayload


class TestItemUrl:
    def test_radarr_links_by_tmdb_id(self) -> None:
        context = ArrContext(url="http://radarr:7878/", slug="693134")

        assert item_url("radarr", context) == "http://radarr:7878/movie/693134"

    def test_sonarr_links_by_title_slug(self) -> None:
        context = ArrContext(url="https://tv.example/sonarr", slug="the-bear")

        assert item_url("sonarr", context) == "https://tv.example/sonarr/series/the-bear"

    @pytest.mark.parametrize(
        "context",
        [
            None,
            ArrContext(slug="693134"),
            ArrContext(url="http://radarr:7878"),
            ArrContext(url="javascript:alert(1)//", slug="1"),
            ArrContext(url="radarr:7878", slug="1"),
        ],
    )
    def test_nothing_unsafe_or_incomplete_becomes_a_link(self, context: ArrContext | None) -> None:
        assert item_url("radarr", context) is None

    def test_the_slug_cannot_escape_its_path_segment(self) -> None:
        context = ArrContext(url="http://radarr", slug="../../system?x=1")

        assert item_url("radarr", context) == "http://radarr/movie/..%2F..%2Fsystem%3Fx%3D1"


class TestPayload:
    def test_strings_from_the_shell_are_typed(self) -> None:
        context = ArrPayload(
            year="2024", original_language="ger", tags="Dubs| 4k ||dubs"
        ).to_context()

        assert context.year == 2024
        assert context.original_language == "ger"
        assert context.tags == ("dubs", "4k")

    @pytest.mark.parametrize("year", ["0", "", "soon"])
    def test_an_unknown_year_is_none(self, year: str) -> None:
        assert ArrPayload(year=year).to_context().year is None

    def test_an_unknown_language_is_none_rather_than_an_error(self) -> None:
        assert ArrPayload(original_language="klingon").to_context().original_language is None

    def test_it_round_trips_through_storage(self) -> None:
        context = ArrPayload(title="Dune", year="2024", tags="a|b").to_context()

        assert ArrContext.from_stored(context.to_dict()) == context
