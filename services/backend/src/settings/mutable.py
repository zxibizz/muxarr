"""Which settings the UI may change, and how a stored override is applied.

Overrides are kept as the same raw strings the environment would have supplied,
so a value takes exactly one validation path whether it arrived from compose or
from the browser.

An environment variable that is explicitly set *locks* its field: whoever wrote
the compose file expects it to be the source of truth, and silently shadowing it
from a database row is the surprising outcome.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, replace

from src.domain.enums import AI_MODES, DEDUPE_MODES
from src.settings.config import (
    MAX_OPERATION_LOG_ENTRIES,
    TRUTHY,
    ConfigError,
    Settings,
    parse_languages,
)

# loguru's levels; ``from_env`` accepts anything, but a typo chosen in a dropdown
# would silence the daemon with no way to notice.
_LOG_LEVELS = ("TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL")


@dataclass(frozen=True, slots=True)
class FieldSpec:
    """One UI-editable setting."""

    name: str
    env: str
    group: str
    coerce: Callable[[str, str], object]
    # Never echoed back over HTTP.
    secret: bool = False


def _as_text(env: str, raw: str) -> object:
    del env
    return raw.strip()


def _as_optional_text(env: str, raw: str) -> object:
    del env
    return raw.strip() or None


def _as_bool(env: str, raw: str) -> object:
    del env
    return raw.strip().lower() in TRUTHY


def _as_int(minimum: int, maximum: int | None = None) -> Callable[[str, str], object]:
    def parse(env: str, raw: str) -> object:
        try:
            value = int(raw.strip())
        except ValueError as exc:
            raise ConfigError(f"{env} must be an integer, got {raw!r}") from exc
        if value < minimum:
            raise ConfigError(f"{env} must be at least {minimum}, got {value}")
        if maximum is not None and value > maximum:
            raise ConfigError(f"{env} must be at most {maximum}, got {value}")
        return value

    return parse


def _as_float(minimum: float) -> Callable[[str, str], object]:
    def parse(env: str, raw: str) -> object:
        try:
            value = float(raw.strip())
        except ValueError as exc:
            raise ConfigError(f"{env} must be a number, got {raw!r}") from exc
        if value < minimum:
            raise ConfigError(f"{env} must be at least {minimum}, got {value}")
        return value

    return parse


def _as_choice(*choices: str, lower: bool = True) -> Callable[[str, str], object]:
    def parse(env: str, raw: str) -> object:
        value = raw.strip().lower() if lower else raw.strip().upper()
        if value not in choices:
            raise ConfigError(f"{env} must be one of {sorted(choices)}, got {raw!r}")
        return value

    return parse


_DEDUPE = _as_choice(*DEDUPE_MODES)
_AI_MODE = _as_choice(*AI_MODES)
_LOG_LEVEL = _as_choice(*_LOG_LEVELS, lower=False)

FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("dedupe", "MUXARR_DEDUPE", "selection", _DEDUPE),
    FieldSpec("skip_image_subtitles", "MUXARR_SKIP_IMAGE_SUBTITLES", "selection", _as_bool),
    FieldSpec("skip_undetermined_language", "MUXARR_SKIP_UNDETERMINED", "selection", _as_bool),
    FieldSpec("max_external_tracks", "MUXARR_MAX_TRACKS", "selection", _as_int(1)),
    FieldSpec("sub_charset", "MUXARR_SUB_CHARSET", "selection", _as_optional_text),
    FieldSpec("keep_audio_languages", "MUXARR_KEEP_AUDIO_LANGUAGES", "selection", parse_languages),
    FieldSpec(
        "keep_subtitle_languages", "MUXARR_KEEP_SUBTITLE_LANGUAGES", "selection", parse_languages
    ),
    FieldSpec("mux_timeout_seconds", "MUXARR_MUX_TIMEOUT", "mux", _as_float(1.0)),
    FieldSpec("free_space_factor", "MUXARR_FREE_SPACE_FACTOR", "mux", _as_float(1.0)),
    FieldSpec("preserve_ownership", "MUXARR_PRESERVE_OWNERSHIP", "mux", _as_bool),
    FieldSpec("max_concurrent_muxes", "MUXARR_MAX_CONCURRENT", "queue", _as_int(1)),
    FieldSpec("job_ttl_seconds", "MUXARR_JOB_TTL", "queue", _as_float(60.0)),
    FieldSpec("history_max_records", "MUXARR_HISTORY_MAX_RECORDS", "queue", _as_int(1)),
    FieldSpec(
        "operation_log_max_entries",
        "MUXARR_OPERATION_LOG_MAX_ENTRIES",
        "queue",
        _as_int(0, MAX_OPERATION_LOG_ENTRIES),
    ),
    FieldSpec("ai_mode", "MUXARR_AI_MODE", "ai", _AI_MODE),
    FieldSpec("ai_base_url", "MUXARR_AI_BASE_URL", "ai", _as_text),
    FieldSpec("ai_api_key", "MUXARR_AI_API_KEY", "ai", _as_optional_text, secret=True),
    FieldSpec("ai_model", "MUXARR_AI_MODEL", "ai", _as_text),
    FieldSpec("ai_timeout_seconds", "MUXARR_AI_TIMEOUT", "ai", _as_float(1.0)),
    FieldSpec("ai_max_entries", "MUXARR_AI_MAX_ENTRIES", "ai", _as_int(1)),
    FieldSpec("ai_name_tracks", "MUXARR_AI_NAME_TRACKS", "ai", _as_bool),
    FieldSpec("log_level", "MUXARR_LOG_LEVEL", "logging", _LOG_LEVEL),
)

BY_NAME: Mapping[str, FieldSpec] = {spec.name: spec for spec in FIELDS}

SECRET_FIELDS = frozenset(spec.name for spec in FIELDS if spec.secret)


class SettingsLockedError(ConfigError):
    """The field is pinned by an environment variable and cannot be edited."""


def locked_fields(env: Mapping[str, str] | None = None) -> frozenset[str]:
    """Names whose environment variable is set, and so may not be edited."""
    source = os.environ if env is None else env
    return frozenset(spec.name for spec in FIELDS if source.get(spec.env, "").strip())


def reject_locked(names: Iterable[str], locked: frozenset[str]) -> None:
    clashes = sorted(set(names) & locked)
    if not clashes:
        return
    pinned = ", ".join(f"{name} ({BY_NAME[name].env})" for name in clashes)
    raise SettingsLockedError(
        f"pinned by the environment and not editable here: {pinned}. "
        "Unset the variable to manage it from the UI."
    )


def apply_overrides(
    base: Settings, overrides: Mapping[str, str], *, locked: frozenset[str] = frozenset()
) -> Settings:
    """Layer stored overrides over the environment-derived settings."""
    values: dict[str, object] = {}
    for name, raw in overrides.items():
        spec = BY_NAME.get(name)
        # A key left behind by an older version is stale, not fatal.
        if spec is None or name in locked:
            continue
        values[name] = spec.coerce(spec.env, raw)

    settings = replace(base, **values)  # type: ignore[arg-type]
    validate(settings)
    return settings


def validate(settings: Settings) -> None:
    """Cross-field rules that no single coercer can see."""
    if settings.ai_enabled and not settings.ai_model:
        raise ConfigError("ai_model is required when ai_mode is not 'off'")


def to_raw(value: object) -> str:
    """Render a typed value back into its environment-string form."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple)):
        return ",".join(str(item) for item in value)
    return str(value)
