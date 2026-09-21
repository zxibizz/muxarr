"""Runtime configuration, loaded from the environment.

Everything is namespaced ``MUXARR_*`` so it can be set directly in a docker
compose file without a config file mount.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from muxarr.errors import MuxarrError
from muxarr.selection import DedupeMode, SelectionPolicy

DEFAULT_PORT = 8710
DEFAULT_HOST = "127.0.0.1"

_TRUTHY = frozenset({"1", "true", "yes", "on"})
_VALID_DEDUPE: frozenset[str] = frozenset({"off", "language", "language_codec"})


class ConfigError(MuxarrError):
    """The environment does not describe a usable configuration."""


@dataclass(frozen=True, slots=True)
class Settings:
    # Every path muxarr may read: download folders and library roots.
    # Writes are additionally restricted to the destination's own directory.
    read_roots: tuple[Path, ...]
    auth_token: str | None = None
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    # Serialised by default: two concurrent remuxes on one spindle is worse than
    # either of them running alone.
    max_concurrent_muxes: int = 1
    scratch_dir: Path | None = None
    dedupe: DedupeMode = "language_codec"
    skip_image_subtitles: bool = False
    skip_undetermined_language: bool = False
    max_external_tracks: int = 24
    mux_timeout_seconds: float = 4 * 60 * 60.0
    free_space_factor: float = 1.05
    preserve_ownership: bool = True
    sub_charset: str | None = None
    log_level: str = "INFO"
    web_dir: Path | None = None
    extra: Mapping[str, str] = field(default_factory=dict)

    @property
    def selection_policy(self) -> SelectionPolicy:
        return SelectionPolicy(
            dedupe=self.dedupe,
            max_external_tracks=self.max_external_tracks,
            skip_image_subtitles=self.skip_image_subtitles,
            skip_undetermined_language=self.skip_undetermined_language,
        )

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        source = os.environ if env is None else env

        roots = _parse_roots(source.get("MUXARR_READ_ROOTS", ""))
        if not roots:
            raise ConfigError(
                "MUXARR_READ_ROOTS is required: a path-separated list of directories "
                "muxarr may read (download folders and library roots)"
            )

        dedupe = source.get("MUXARR_DEDUPE", "language_codec").strip().lower()
        if dedupe not in _VALID_DEDUPE:
            raise ConfigError(
                f"MUXARR_DEDUPE must be one of {sorted(_VALID_DEDUPE)}, got {dedupe!r}"
            )

        scratch = source.get("MUXARR_SCRATCH_DIR", "").strip()
        web_dir = source.get("MUXARR_WEB_DIR", "").strip()

        return cls(
            read_roots=roots,
            auth_token=source.get("MUXARR_TOKEN") or None,
            host=source.get("MUXARR_HOST", DEFAULT_HOST),
            port=_parse_int(source, "MUXARR_PORT", DEFAULT_PORT),
            max_concurrent_muxes=max(1, _parse_int(source, "MUXARR_MAX_CONCURRENT", 1)),
            scratch_dir=Path(scratch) if scratch else None,
            dedupe=dedupe,  # type: ignore[arg-type]
            skip_image_subtitles=_parse_bool(source, "MUXARR_SKIP_IMAGE_SUBTITLES"),
            skip_undetermined_language=_parse_bool(source, "MUXARR_SKIP_UNDETERMINED"),
            max_external_tracks=_parse_int(source, "MUXARR_MAX_TRACKS", 24),
            mux_timeout_seconds=_parse_float(source, "MUXARR_MUX_TIMEOUT", 4 * 60 * 60.0),
            free_space_factor=_parse_float(source, "MUXARR_FREE_SPACE_FACTOR", 1.05),
            preserve_ownership=_parse_bool(source, "MUXARR_PRESERVE_OWNERSHIP", default=True),
            sub_charset=source.get("MUXARR_SUB_CHARSET") or None,
            log_level=source.get("MUXARR_LOG_LEVEL", "INFO").upper(),
            web_dir=Path(web_dir).expanduser() if web_dir else None,
        )


def _parse_roots(raw: str) -> tuple[Path, ...]:
    return tuple(Path(part).expanduser() for part in raw.split(os.pathsep) if part.strip())


def _parse_bool(source: Mapping[str, str], key: str, *, default: bool = False) -> bool:
    raw = source.get(key)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in _TRUTHY


def _parse_int(source: Mapping[str, str], key: str, default: int) -> int:
    raw = source.get(key)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{key} must be an integer, got {raw!r}") from exc


def _parse_float(source: Mapping[str, str], key: str, default: float) -> float:
    raw = source.get(key)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"{key} must be a number, got {raw!r}") from exc
