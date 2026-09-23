from __future__ import annotations

import os
from pathlib import Path

import pytest

from src.settings.config import (
    DEFAULT_AI_BASE_URL,
    DEFAULT_DB_URL,
    DEFAULT_PORT,
    ConfigError,
    Settings,
)


def env(**overrides: str) -> dict[str, str]:
    base = {"MUXARR_READ_ROOTS": f"/downloads{os.pathsep}/library"}
    base.update(overrides)
    return base


def test_read_roots_are_required() -> None:
    with pytest.raises(ConfigError, match="MUXARR_READ_ROOTS is required"):
        Settings.from_env({})


def test_read_roots_are_split_on_the_path_separator() -> None:
    settings = Settings.from_env(env())

    assert settings.read_roots == (Path("/downloads"), Path("/library"))


def test_blank_root_entries_are_ignored() -> None:
    settings = Settings.from_env(
        env(MUXARR_READ_ROOTS=f"/downloads{os.pathsep}{os.pathsep}/library{os.pathsep}")
    )

    assert settings.read_roots == (Path("/downloads"), Path("/library"))


def test_root_entries_are_stripped_of_whitespace_and_quotes() -> None:
    settings = Settings.from_env(env(MUXARR_READ_ROOTS=f'  /downloads {os.pathsep} "/library"'))

    assert settings.read_roots == (Path("/downloads"), Path("/library"))


def test_relative_roots_are_rejected() -> None:
    with pytest.raises(ConfigError, match="must be absolute paths"):
        Settings.from_env(env(MUXARR_READ_ROOTS="media"))


def test_defaults() -> None:
    settings = Settings.from_env(env())

    assert settings.port == DEFAULT_PORT
    assert settings.auth_token is None
    assert settings.max_concurrent_muxes == 1
    assert settings.scratch_dir is None
    assert settings.dedupe == "language_codec"
    assert settings.preserve_ownership is True
    assert settings.history_max_records == 200


def test_history_cap_is_at_least_one() -> None:
    assert Settings.from_env(env(MUXARR_HISTORY_MAX_RECORDS="0")).history_max_records == 1


class TestDbUrl:
    def test_defaults_to_sqlite_in_config(self) -> None:
        assert Settings.from_env(env()).db_url == DEFAULT_DB_URL

    @pytest.mark.parametrize(
        "raw",
        [
            "postgres://u:p@db:5432/muxarr",
            "postgresql://u:p@db:5432/muxarr",
            "POSTGRESQL://u:p@db:5432/muxarr",
        ],
    )
    def test_bare_postgres_urls_get_the_async_driver(self, raw: str) -> None:
        settings = Settings.from_env(env(MUXARR_DB_URL=raw))

        assert settings.db_url == "postgresql+asyncpg://u:p@db:5432/muxarr"

    @pytest.mark.parametrize(
        "raw",
        [
            "sqlite+aiosqlite:////config/muxarr.db",
            "postgresql+asyncpg://u:p@db/muxarr",
            "postgresql+psycopg://u:p@db/muxarr",
        ],
    )
    def test_supported_urls_pass_through(self, raw: str) -> None:
        assert Settings.from_env(env(MUXARR_DB_URL=raw)).db_url == raw

    def test_an_unsupported_driver_is_rejected_without_echoing_the_password(self) -> None:
        with pytest.raises(ConfigError, match="mysql") as excinfo:
            Settings.from_env(env(MUXARR_DB_URL="mysql://u:hunter2@db/muxarr"))

        assert "hunter2" not in str(excinfo.value)

    def test_a_non_url_is_rejected_without_echoing_it(self) -> None:
        with pytest.raises(ConfigError, match="must be a URL") as excinfo:
            Settings.from_env(env(MUXARR_DB_URL="u:hunter2@db"))

        assert "hunter2" not in str(excinfo.value)


@pytest.mark.parametrize("raw", ["1", "true", "TRUE", "yes", "on"])
def test_truthy_booleans(raw: str) -> None:
    assert Settings.from_env(env(MUXARR_SKIP_IMAGE_SUBTITLES=raw)).skip_image_subtitles


@pytest.mark.parametrize("raw", ["0", "false", "no", "off", "", "   "])
def test_falsy_booleans(raw: str) -> None:
    assert not Settings.from_env(env(MUXARR_SKIP_IMAGE_SUBTITLES=raw)).skip_image_subtitles


def test_preserve_ownership_defaults_true_but_can_be_disabled() -> None:
    assert Settings.from_env(env()).preserve_ownership is True
    assert Settings.from_env(env(MUXARR_PRESERVE_OWNERSHIP="false")).preserve_ownership is False


def test_invalid_dedupe_is_rejected() -> None:
    with pytest.raises(ConfigError, match="MUXARR_DEDUPE"):
        Settings.from_env(env(MUXARR_DEDUPE="whatever"))


def test_invalid_port_is_rejected() -> None:
    with pytest.raises(ConfigError, match="must be an integer"):
        Settings.from_env(env(MUXARR_PORT="eight thousand"))


def test_invalid_float_is_rejected() -> None:
    with pytest.raises(ConfigError, match="must be a number"):
        Settings.from_env(env(MUXARR_FREE_SPACE_FACTOR="lots"))


def test_concurrency_is_clamped_to_at_least_one() -> None:
    assert Settings.from_env(env(MUXARR_MAX_CONCURRENT="0")).max_concurrent_muxes == 1
    assert Settings.from_env(env(MUXARR_MAX_CONCURRENT="-5")).max_concurrent_muxes == 1


def test_empty_token_is_treated_as_unset() -> None:
    assert Settings.from_env(env(MUXARR_TOKEN="")).auth_token is None


def test_selection_policy_is_derived_from_settings() -> None:
    settings = Settings.from_env(
        env(MUXARR_DEDUPE="language", MUXARR_MAX_TRACKS="3", MUXARR_SKIP_UNDETERMINED="yes")
    )

    policy = settings.selection_policy

    assert policy.dedupe == "language"
    assert policy.max_external_tracks == 3
    assert policy.skip_undetermined_language is True


class TestKeepLanguages:
    def test_empty_by_default(self) -> None:
        settings = Settings.from_env(env())

        assert settings.keep_audio_languages == ()
        assert settings.selection_policy.keep_subtitle_languages == frozenset()

    def test_aliases_are_normalised_in_order_without_duplicates(self) -> None:
        settings = Settings.from_env(env(MUXARR_KEEP_AUDIO_LANGUAGES=" EN, russian ,deu,eng, und,"))

        assert settings.keep_audio_languages == ("eng", "rus", "ger", "und")

    def test_an_unknown_language_is_rejected(self) -> None:
        with pytest.raises(ConfigError, match=r"MUXARR_KEEP_SUBTITLE_LANGUAGES.*klingon"):
            Settings.from_env(env(MUXARR_KEEP_SUBTITLE_LANGUAGES="eng,klingon"))

    def test_they_reach_the_selection_policy(self) -> None:
        policy = Settings.from_env(
            env(MUXARR_KEEP_AUDIO_LANGUAGES="eng", MUXARR_KEEP_SUBTITLE_LANGUAGES="rus")
        ).selection_policy

        assert policy.keep_audio_languages == frozenset({"eng"})
        assert policy.keep_subtitle_languages == frozenset({"rus"})


class TestAiMode:
    def test_is_off_by_default(self) -> None:
        settings = Settings.from_env(env())

        assert settings.ai_mode == "off"
        assert settings.ai_enabled is False
        assert settings.ai_api_key is None
        assert settings.ai_base_url == DEFAULT_AI_BASE_URL

    @pytest.mark.parametrize("mode", ["fallback", "always", "verify"])
    def test_valid_modes(self, mode: str) -> None:
        settings = Settings.from_env(env(MUXARR_AI_MODE=mode, MUXARR_AI_MODEL="tiny"))

        assert settings.ai_mode == mode
        assert settings.ai_enabled is True

    def test_invalid_mode_is_rejected(self) -> None:
        with pytest.raises(ConfigError, match="MUXARR_AI_MODE"):
            Settings.from_env(env(MUXARR_AI_MODE="magic"))

    def test_mode_is_case_insensitive(self) -> None:
        assert Settings.from_env(env(MUXARR_AI_MODE="FALLBACK", MUXARR_AI_MODEL="t")).ai_mode == (
            "fallback"
        )

    def test_model_is_required_once_enabled(self) -> None:
        with pytest.raises(ConfigError, match="MUXARR_AI_MODEL is required"):
            Settings.from_env(env(MUXARR_AI_MODE="always"))

    def test_model_is_not_required_while_off(self) -> None:
        assert Settings.from_env(env()).ai_model == ""

    def test_a_keyless_local_provider_is_allowed(self) -> None:
        settings = Settings.from_env(
            env(
                MUXARR_AI_MODE="fallback",
                MUXARR_AI_MODEL="qwen2.5:7b",
                MUXARR_AI_BASE_URL="http://127.0.0.1:11434/v1",
            )
        )

        assert settings.ai_api_key is None
        assert settings.ai_base_url == "http://127.0.0.1:11434/v1"

    def test_entry_cap_is_at_least_one(self) -> None:
        assert Settings.from_env(env(MUXARR_AI_MAX_ENTRIES="0")).ai_max_entries == 1
