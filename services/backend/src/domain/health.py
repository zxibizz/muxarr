"""Configuration problems worth showing the user, as the *arr apps' System > Status does."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal, get_args

HealthLevel = Literal["notice", "warning", "error"]

# Stable keys, so the UI and tests never match on the message's wording.
HealthCode = Literal[
    "worker_offline",
    "mkvmerge_missing",
    "mkvmerge_outdated",
    "read_root_missing",
    "read_root_unreadable",
    "scratch_dir_unusable",
    "sqlite_split",
    "login_off",
    "proxies_untrusted",
]
HEALTH_CODES: tuple[HealthCode, ...] = get_args(HealthCode)
HEALTH_LEVELS: tuple[HealthLevel, ...] = get_args(HealthLevel)


@dataclass(frozen=True, slots=True)
class HealthIssue:
    level: HealthLevel
    code: HealthCode
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"level": self.level, "code": self.code, "message": self.message}

    @classmethod
    def from_stored(cls, data: Mapping[str, Any]) -> HealthIssue | None:
        """None for a row written by a version that knew codes this one does not."""
        level, code = data.get("level"), data.get("code")
        if level not in HEALTH_LEVELS or code not in HEALTH_CODES:
            return None
        return cls(level=level, code=code, message=str(data.get("message") or ""))
