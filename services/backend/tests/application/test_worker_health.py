from __future__ import annotations

import os
from pathlib import Path

import pytest

from src.application.use_cases.system.health import CheckWorkerHealthUseCase
from src.settings.config import Settings
from tests.stubs import StubMuxer


class VersionedMuxer(StubMuxer):
    def __init__(self, version: tuple[int, int] | None) -> None:
        super().__init__()
        self._version = version

    def version(self) -> tuple[int, int] | None:
        return self._version


def check(
    tmp_path: Path, *, version: tuple[int, int] | None = (90, 0), **overrides: object
) -> list[tuple[str, str]]:
    settings = Settings(**{"read_roots": (tmp_path,), **overrides})  # type: ignore[arg-type]
    issues = CheckWorkerHealthUseCase(settings=settings, muxer=VersionedMuxer(version)).execute()
    return [(issue.level, issue.code) for issue in issues]


def test_a_sound_setup_has_nothing_to_report(tmp_path: Path) -> None:
    assert check(tmp_path) == []


def test_a_missing_mkvmerge_is_an_error(tmp_path: Path) -> None:
    assert check(tmp_path, version=None) == [("error", "mkvmerge_missing")]


def test_an_old_mkvmerge_is_only_a_notice(tmp_path: Path) -> None:
    assert check(tmp_path, version=(51, 0)) == [("notice", "mkvmerge_outdated")]


def test_an_unmounted_read_root_is_an_error(tmp_path: Path) -> None:
    missing = tmp_path / "media"

    assert check(tmp_path, read_roots=(tmp_path, missing)) == [("error", "read_root_missing")]


@pytest.mark.skipif(os.getuid() == 0, reason="root reads everything")
def test_an_unreadable_read_root_is_an_error(tmp_path: Path) -> None:
    locked = tmp_path / "locked"
    locked.mkdir(mode=0o000)
    try:
        assert check(tmp_path, read_roots=(locked,)) == [("error", "read_root_unreadable")]
    finally:
        locked.chmod(0o755)


def test_a_scratch_dir_that_will_be_created_is_fine(tmp_path: Path) -> None:
    assert check(tmp_path, scratch_dir=tmp_path / "scratch" / "deeper") == []


@pytest.mark.skipif(os.getuid() == 0, reason="root writes everything")
def test_an_unwritable_scratch_dir_is_an_error(tmp_path: Path) -> None:
    scratch = tmp_path / "scratch"
    scratch.mkdir(mode=0o555)
    try:
        assert check(tmp_path, scratch_dir=scratch) == [("error", "scratch_dir_unusable")]
    finally:
        scratch.chmod(0o755)
