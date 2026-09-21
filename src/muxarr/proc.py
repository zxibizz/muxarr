"""Subprocess helper.

Every external command in muxarr goes through :func:`run`. Two invariants:

* commands are always argv lists, never shell strings (no ``shell=True`` anywhere);
* long-running media tools get de-prioritised so a remux cannot starve a Plex
  stream reading from the same spindle.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from muxarr.errors import ToolNotFoundError

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 60.0


@dataclass(frozen=True, slots=True)
class CommandResult:
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    def tail(self, lines: int = 20) -> str:
        """Last few lines of stderr, for error messages."""
        return "\n".join(self.stderr.strip().splitlines()[-lines:])


def resolve_tool(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise ToolNotFoundError(f"required binary not found on PATH: {name}")
    return path


def has_tool(name: str) -> bool:
    return shutil.which(name) is not None


def deprioritise_prefix(*, nice_level: int = 19, io_class: int = 3) -> list[str]:
    """Build a ``nice``/``ionice`` prefix, skipping whatever isn't available.

    ``ionice -c3`` (idle) is the part that actually matters for spinning disks, but
    it is util-linux only, so it is absent on macOS and in slim containers.
    """
    prefix: list[str] = []
    if shutil.which("nice"):
        prefix += ["nice", "-n", str(nice_level)]
    if shutil.which("ionice"):
        prefix += ["ionice", "-c", str(io_class)]
    return prefix


def run(
    argv: Sequence[str],
    *,
    timeout: float | None = DEFAULT_TIMEOUT,
    cwd: Path | None = None,
    deprioritise: bool = False,
) -> CommandResult:
    """Run a command to completion and capture its output.

    Never raises on a non-zero exit; callers decide what a failure means.
    """
    full: list[str] = [*deprioritise_prefix(), *argv] if deprioritise else list(argv)
    log.debug("exec: %s", full)
    try:
        completed = subprocess.run(  # noqa: S603
            full,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = _as_text(exc.stdout)
        stderr = _as_text(exc.stderr)
        return CommandResult(tuple(full), 124, stdout, f"{stderr}\ntimed out after {timeout}s")
    except FileNotFoundError as exc:
        raise ToolNotFoundError(f"binary not found: {full[0]}") from exc

    return CommandResult(tuple(full), completed.returncode, completed.stdout, completed.stderr)


def _as_text(raw: str | bytes | None) -> str:
    if raw is None:
        return ""
    if isinstance(raw, bytes):
        return raw.decode("utf-8", errors="replace")
    return raw
