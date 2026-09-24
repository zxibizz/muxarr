"""Runtime configuration, loaded from the environment.

Everything is namespaced ``MUXARR_*`` so it can be set directly in a docker
compose file without a config file mount.
"""

from __future__ import annotations

import ipaddress
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypeVar

from src.domain.auth import DEFAULT_LOCAL_NETWORKS, IPNetwork, credentials_problem
from src.domain.enums import (
    AI_MODES,
    AUTH_METHODS,
    AUTH_REQUIRED,
    DEDUPE_MODES,
    UNDETERMINED,
    AiMode,
    AuthMethod,
    AuthRequired,
    DedupeMode,
)
from src.domain.errors import MuxarrError
from src.domain.language import normalise_language
from src.domain.selection import SelectionPolicy

DEFAULT_PORT = 8710
DEFAULT_HOST = "127.0.0.1"

# The container mounts a volume here; anything else has to set MUXARR_DB_URL.
DEFAULT_DB_URL = "sqlite+aiosqlite:////config/muxarr.db"

SUPPORTED_DB_SCHEMES = ("sqlite+aiosqlite", "postgresql+asyncpg", "postgresql+psycopg")
# Bare postgres URLs would make SQLAlchemy reach for psycopg2, which is not installed.
_DB_SCHEME_ALIASES = {"postgres": "postgresql+asyncpg", "postgresql": "postgresql+asyncpg"}

DEFAULT_AI_BASE_URL = "https://api.openai.com/v1"

# The log is stored inline on the row it explains, so it is capped well below
# anything that would make the history table awkward to read back.
MAX_OPERATION_LOG_ENTRIES = 5000

TRUTHY = frozenset({"1", "true", "yes", "on"})

_Choice = TypeVar("_Choice", bound=str)


class ConfigError(MuxarrError):
    """The environment does not describe a usable configuration."""


@dataclass(frozen=True, slots=True)
class Settings:
    # Every path muxarr may read: download folders and library roots.
    # Writes are additionally restricted to the destination's own directory.
    read_roots: tuple[Path, ...]
    # Pins the API key; left unset, one is generated and stored on first start.
    api_key: str | None = field(default=None, repr=False)
    auth_method: AuthMethod = "forms"
    auth_required: AuthRequired = "enabled"
    # Proxies whose X-Forwarded-For names the real caller; nobody else's is believed.
    trusted_proxies: tuple[IPNetwork, ...] = ()
    # Callers that "disabled_for_local_addresses" lets in without a login.
    local_networks: tuple[IPNetwork, ...] = DEFAULT_LOCAL_NETWORKS
    # Set together, these pin the UI login and overwrite the stored user on start.
    username: str | None = None
    password: str | None = field(default=None, repr=False)
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    # Serialised by default: two concurrent remuxes on one spindle is worse than
    # either of them running alone.
    max_concurrent_muxes: int = 1
    # How long a finished job stays readable. The shim fails the import if its
    # job has already been evicted, so this must outlast any plausible poll gap.
    job_ttl_seconds: float = 60 * 60.0
    # Ceiling on a single long-poll hold; keeps requests short enough to survive
    # proxy idle timeouts.
    max_poll_wait_seconds: float = 60.0
    # The history is a recent-activity log, not an archive; the worker trims it.
    history_max_records: int = 200
    # How many log records are kept to explain one import. 0 stops the capture.
    operation_log_max_entries: int = 500
    scratch_dir: Path | None = None
    dedupe: DedupeMode = "language_codec"
    skip_image_subtitles: bool = False
    skip_undetermined_language: bool = False
    max_external_tracks: int = 24
    # Languages to keep; any other track in the source or a sidecar is dropped.
    keep_audio_languages: tuple[str, ...] = ()
    keep_subtitle_languages: tuple[str, ...] = ()
    mux_timeout_seconds: float = 4 * 60 * 60.0
    free_space_factor: float = 1.05
    preserve_ownership: bool = True
    sub_charset: str | None = None
    log_level: str = "INFO"
    # Emit one JSON object per record instead of the human-readable console line.
    log_json: bool = False
    db_url: str = DEFAULT_DB_URL
    # Off by default: enabling it sends release folder and file NAMES to a third party.
    ai_mode: AiMode = "off"
    ai_base_url: str = DEFAULT_AI_BASE_URL
    ai_api_key: str | None = None
    ai_model: str = ""
    ai_timeout_seconds: float = 30.0
    # A season pack can hold thousands of files; above this the AI path is skipped
    # entirely rather than sending (and paying for) an enormous listing.
    ai_max_entries: int = 200
    # Let the provider write the track names even on releases the filenames already
    # settled, which costs a request per import that would otherwise be free.
    ai_name_tracks: bool = False
    extra: Mapping[str, str] = field(default_factory=dict)

    @property
    def ai_enabled(self) -> bool:
        return self.ai_mode != "off"

    @property
    def selection_policy(self) -> SelectionPolicy:
        return SelectionPolicy(
            dedupe=self.dedupe,
            max_external_tracks=self.max_external_tracks,
            skip_image_subtitles=self.skip_image_subtitles,
            skip_undetermined_language=self.skip_undetermined_language,
            keep_audio_languages=frozenset(self.keep_audio_languages),
            keep_subtitle_languages=frozenset(self.keep_subtitle_languages),
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

        dedupe = parse_choice(
            "MUXARR_DEDUPE", source.get("MUXARR_DEDUPE", "language_codec"), DEDUPE_MODES
        )

        scratch = source.get("MUXARR_SCRATCH_DIR", "").strip()

        ai_mode = parse_choice("MUXARR_AI_MODE", source.get("MUXARR_AI_MODE") or "off", AI_MODES)
        ai_model = source.get("MUXARR_AI_MODEL", "").strip()
        if ai_mode != "off" and not ai_model:
            raise ConfigError("MUXARR_AI_MODEL is required when MUXARR_AI_MODE is not 'off'")

        username = source.get("MUXARR_USERNAME", "").strip() or None
        password = source.get("MUXARR_PASSWORD") or None
        if (username is None) != (password is None):
            raise ConfigError("MUXARR_USERNAME and MUXARR_PASSWORD must be set together")
        if username is not None and password is not None:
            problem = credentials_problem(username, password)
            if problem is not None:
                raise ConfigError(f"MUXARR_USERNAME/MUXARR_PASSWORD: {problem}")

        return cls(
            read_roots=roots,
            api_key=source.get("MUXARR_API_KEY", "").strip() or None,
            auth_method=parse_choice(
                "MUXARR_AUTH_METHOD", source.get("MUXARR_AUTH_METHOD") or "forms", AUTH_METHODS
            ),
            auth_required=parse_choice(
                "MUXARR_AUTH_REQUIRED",
                source.get("MUXARR_AUTH_REQUIRED") or "enabled",
                AUTH_REQUIRED,
            ),
            trusted_proxies=parse_networks(
                "MUXARR_TRUSTED_PROXIES", source.get("MUXARR_TRUSTED_PROXIES", "")
            ),
            local_networks=parse_networks(
                "MUXARR_LOCAL_NETWORKS", source.get("MUXARR_LOCAL_NETWORKS", "")
            )
            or DEFAULT_LOCAL_NETWORKS,
            username=username,
            password=password,
            host=source.get("MUXARR_HOST", DEFAULT_HOST),
            port=_parse_int(source, "MUXARR_PORT", DEFAULT_PORT),
            max_concurrent_muxes=max(1, _parse_int(source, "MUXARR_MAX_CONCURRENT", 1)),
            job_ttl_seconds=_parse_float(source, "MUXARR_JOB_TTL", 60 * 60.0),
            max_poll_wait_seconds=_parse_float(source, "MUXARR_MAX_POLL_WAIT", 60.0),
            history_max_records=max(1, _parse_int(source, "MUXARR_HISTORY_MAX_RECORDS", 200)),
            operation_log_max_entries=min(
                MAX_OPERATION_LOG_ENTRIES,
                max(0, _parse_int(source, "MUXARR_OPERATION_LOG_MAX_ENTRIES", 500)),
            ),
            scratch_dir=Path(scratch) if scratch else None,
            dedupe=dedupe,
            skip_image_subtitles=_parse_bool(source, "MUXARR_SKIP_IMAGE_SUBTITLES"),
            skip_undetermined_language=_parse_bool(source, "MUXARR_SKIP_UNDETERMINED"),
            max_external_tracks=_parse_int(source, "MUXARR_MAX_TRACKS", 24),
            keep_audio_languages=parse_languages(
                "MUXARR_KEEP_AUDIO_LANGUAGES", source.get("MUXARR_KEEP_AUDIO_LANGUAGES", "")
            ),
            keep_subtitle_languages=parse_languages(
                "MUXARR_KEEP_SUBTITLE_LANGUAGES", source.get("MUXARR_KEEP_SUBTITLE_LANGUAGES", "")
            ),
            mux_timeout_seconds=_parse_float(source, "MUXARR_MUX_TIMEOUT", 4 * 60 * 60.0),
            free_space_factor=_parse_float(source, "MUXARR_FREE_SPACE_FACTOR", 1.05),
            preserve_ownership=_parse_bool(source, "MUXARR_PRESERVE_OWNERSHIP", default=True),
            sub_charset=source.get("MUXARR_SUB_CHARSET") or None,
            log_level=source.get("MUXARR_LOG_LEVEL", "INFO").upper(),
            log_json=_parse_bool(source, "MUXARR_LOG_JSON"),
            db_url=normalise_db_url(source.get("MUXARR_DB_URL", "")),
            ai_mode=ai_mode,
            ai_base_url=source.get("MUXARR_AI_BASE_URL", "").strip() or DEFAULT_AI_BASE_URL,
            ai_api_key=source.get("MUXARR_AI_API_KEY") or None,
            ai_model=ai_model,
            ai_timeout_seconds=_parse_float(source, "MUXARR_AI_TIMEOUT", 30.0),
            ai_max_entries=max(1, _parse_int(source, "MUXARR_AI_MAX_ENTRIES", 200)),
            ai_name_tracks=_parse_bool(source, "MUXARR_AI_NAME_TRACKS"),
        )


def _parse_roots(raw: str) -> tuple[Path, ...]:
    roots = []
    for part in raw.split(os.pathsep):
        # Surrounding whitespace and quotes survive some env_file/shell paths and
        # would otherwise become a silently unmatchable (or cwd-relative) root.
        cleaned = part.strip().strip("\"'").strip()
        if not cleaned:
            continue
        root = Path(cleaned).expanduser()
        if not root.is_absolute():
            raise ConfigError(f"MUXARR_READ_ROOTS entries must be absolute paths, got {part!r}")
        roots.append(root)
    return tuple(roots)


def normalise_db_url(raw: str) -> str:
    url = raw.strip() or DEFAULT_DB_URL
    scheme, sep, rest = url.partition("://")
    if not sep:
        raise ConfigError("MUXARR_DB_URL must be a URL such as postgresql+asyncpg://host/db")
    scheme = _DB_SCHEME_ALIASES.get(scheme.lower(), scheme.lower())
    # Only the scheme is echoed: the rest of the URL may carry a password.
    if scheme not in SUPPORTED_DB_SCHEMES:
        raise ConfigError(
            f"MUXARR_DB_URL must use one of {list(SUPPORTED_DB_SCHEMES)}, got {scheme!r}"
        )
    return f"{scheme}://{rest}"


def parse_languages(env: str, raw: str) -> tuple[str, ...]:
    """A comma-separated language list as canonical ISO 639-2/B codes, in order, deduplicated."""
    codes: list[str] = []
    for part in raw.split(","):
        token = part.strip().lower()
        if not token:
            continue
        code = UNDETERMINED if token == UNDETERMINED else normalise_language(token)
        if code is None:
            raise ConfigError(f"{env} holds an unknown language {part.strip()!r}")
        if code not in codes:
            codes.append(code)
    return tuple(codes)


def parse_networks(env: str, raw: str) -> tuple[IPNetwork, ...]:
    """Comma-separated addresses and CIDR networks; a bare address is a network of one."""
    networks: list[IPNetwork] = []
    for part in raw.split(","):
        token = part.strip()
        if not token:
            continue
        try:
            network = ipaddress.ip_network(token, strict=False)
        except ValueError as exc:
            raise ConfigError(
                f"{env} holds {token!r}, which is not an IP address or network"
            ) from exc
        if network not in networks:
            networks.append(network)
    return tuple(networks)


def parse_choice(env: str, raw: str, choices: tuple[_Choice, ...]) -> _Choice:
    value = raw.strip().lower()
    for choice in choices:
        if value == choice:
            return choice
    raise ConfigError(f"{env} must be one of {sorted(choices)}, got {raw!r}")


def _parse_bool(source: Mapping[str, str], key: str, *, default: bool = False) -> bool:
    raw = source.get(key)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in TRUTHY


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
