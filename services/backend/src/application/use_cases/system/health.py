"""What the worker can see about its own setup and nobody else can.

In a split deployment the web container has no media mounts and may not even
share a filesystem with the worker, so these checks run where the muxing does
and are reported through the ``worker_state`` row.
"""

from __future__ import annotations

import os

from src.application.interfaces.muxer import Muxer
from src.domain.health import HealthIssue
from src.settings.config import Settings

# mkvtoolnix 58 added the hearing-impaired flag; older releases still mux.
FLAGS_MIN_MKVMERGE = 58


class CheckWorkerHealthUseCase:
    def __init__(self, *, settings: Settings, muxer: Muxer) -> None:
        self._settings = settings
        self._muxer = muxer

    def execute(self) -> list[HealthIssue]:
        """Synchronous: it stats mounts and runs ``mkvmerge --version``."""
        return [*self._toolchain(), *self._roots(), *self._scratch()]

    def _toolchain(self) -> list[HealthIssue]:
        version = self._muxer.version()
        if version is None:
            return [
                HealthIssue(
                    "error",
                    "mkvmerge_missing",
                    "mkvmerge was not found in the worker, so every import is left to *arr.",
                )
            ]
        if version[0] < FLAGS_MIN_MKVMERGE:
            return [
                HealthIssue(
                    "notice",
                    "mkvmerge_outdated",
                    f"mkvmerge {version[0]}.{version[1]} predates {FLAGS_MIN_MKVMERGE}: "
                    "hearing-impaired tracks are embedded without their flag.",
                )
            ]
        return []

    def _roots(self) -> list[HealthIssue]:
        issues = []
        for root in self._settings.read_roots:
            if not root.is_dir():
                issues.append(
                    HealthIssue(
                        "error",
                        "read_root_missing",
                        f"Read root {root} does not exist in the worker. Mount it at the same "
                        "path as in Radarr/Sonarr, or every import under it is deferred.",
                    )
                )
            elif not os.access(root, os.R_OK | os.X_OK):
                issues.append(
                    HealthIssue(
                        "error",
                        "read_root_unreadable",
                        f"Read root {root} is not readable by uid {os.getuid()}. "
                        "Check PUID/PGID against the owner of your media.",
                    )
                )
        return issues

    def _scratch(self) -> list[HealthIssue]:
        scratch = self._settings.scratch_dir
        if scratch is None:
            return []
        # A missing scratch dir is created on first use, so its nearest parent is what counts.
        existing = next((p for p in (scratch, *scratch.parents) if p.exists()), scratch)
        if existing.is_dir() and os.access(existing, os.W_OK | os.X_OK):
            return []
        return [
            HealthIssue(
                "error",
                "scratch_dir_unusable",
                f"MUXARR_SCRATCH_DIR {scratch} is not writable by uid {os.getuid()}, "
                "so every mux fails.",
            )
        ]
