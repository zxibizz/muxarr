from __future__ import annotations

import os
from pathlib import Path

import pytest

from muxarr.config import DEFAULT_PORT, ConfigError, Settings


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
    settings = Settings.from_env(
        env(MUXARR_READ_ROOTS=f'  /downloads {os.pathsep} "/library"')
    )

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
