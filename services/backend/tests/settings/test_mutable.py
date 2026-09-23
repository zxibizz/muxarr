"""Layering stored overrides onto the environment-derived settings."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.settings.config import ConfigError, Settings
from src.settings.mutable import (
    FIELDS,
    SettingsLockedError,
    apply_overrides,
    locked_fields,
    reject_locked,
    to_raw,
)

BASE = Settings(read_roots=(Path("/downloads"),))


class TestApply:
    def test_an_override_replaces_the_environment_value(self) -> None:
        applied = apply_overrides(BASE, {"dedupe": "language"})

        assert applied.dedupe == "language"

    def test_untouched_fields_keep_their_environment_value(self) -> None:
        applied = apply_overrides(BASE, {"dedupe": "off"})

        assert applied.max_external_tracks == BASE.max_external_tracks

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [("true", True), ("false", False), ("1", True), ("no", False)],
    )
    def test_booleans_round_trip_through_their_string_form(self, raw: str, expected: bool) -> None:
        assert apply_overrides(BASE, {"preserve_ownership": raw}).preserve_ownership is expected

    def test_an_empty_string_clears_an_optional_field(self) -> None:
        assert apply_overrides(BASE, {"sub_charset": ""}).sub_charset is None

    def test_a_language_list_round_trips_through_its_string_form(self) -> None:
        applied = apply_overrides(
            BASE, {"keep_audio_languages": to_raw(["eng", "ru"]), "keep_subtitle_languages": ""}
        )

        assert applied.keep_audio_languages == ("eng", "rus")
        assert applied.keep_subtitle_languages == ()

    def test_a_key_from_an_older_version_is_ignored(self) -> None:
        """A removed setting must not stop the daemon from starting."""
        assert apply_overrides(BASE, {"gone_in_a_later_release": "x"}) == BASE

    def test_a_locked_field_is_not_applied(self) -> None:
        applied = apply_overrides(BASE, {"dedupe": "off"}, locked=frozenset({"dedupe"}))

        assert applied.dedupe == BASE.dedupe

    @pytest.mark.parametrize(
        ("name", "raw"),
        [
            ("dedupe", "nonsense"),
            ("max_external_tracks", "several"),
            ("max_concurrent_muxes", "0"),
            ("free_space_factor", "0.5"),
            ("log_level", "CHATTY"),
            ("ai_mode", "maybe"),
            ("keep_audio_languages", "eng,elvish"),
        ],
    )
    def test_an_unusable_value_is_rejected(self, name: str, raw: str) -> None:
        with pytest.raises(ConfigError):
            apply_overrides(BASE, {name: raw})

    def test_enabling_ai_without_a_model_is_rejected(self) -> None:
        with pytest.raises(ConfigError):
            apply_overrides(BASE, {"ai_mode": "always"})

    def test_enabling_ai_with_a_model_is_accepted(self) -> None:
        applied = apply_overrides(BASE, {"ai_mode": "always", "ai_model": "tiny"})

        assert applied.ai_enabled


class TestLocking:
    def test_a_set_variable_locks_its_field(self) -> None:
        assert locked_fields({"MUXARR_DEDUPE": "off"}) == frozenset({"dedupe"})

    def test_a_blank_variable_does_not_lock(self) -> None:
        assert locked_fields({"MUXARR_DEDUPE": "  "}) == frozenset()

    def test_rejecting_names_the_variable_to_unset(self) -> None:
        with pytest.raises(SettingsLockedError, match="MUXARR_DEDUPE"):
            reject_locked(["dedupe"], frozenset({"dedupe"}))

    def test_unpinned_names_pass(self) -> None:
        reject_locked(["dedupe"], frozenset({"ai_model"}))


class TestRendering:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (True, "true"),
            (False, "false"),
            (None, ""),
            (12, "12"),
            (1.5, "1.5"),
            ("x", "x"),
            (["eng", "rus"], "eng,rus"),
            ((), ""),
        ],
    )
    def test_values_render_to_their_environment_form(self, value: object, expected: str) -> None:
        assert to_raw(value) == expected

    def test_every_field_names_a_real_setting(self) -> None:
        """A typo here would silently make a field uneditable."""
        for spec in FIELDS:
            assert hasattr(BASE, spec.name), spec.name
