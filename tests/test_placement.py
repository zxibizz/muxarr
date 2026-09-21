from __future__ import annotations

import os
from pathlib import Path

import pytest

from muxarr.errors import InsufficientSpaceError, PlacementError
from muxarr.placement import (
    PlacementPolicy,
    copy_attributes,
    ensure_free_space,
    finalise,
    same_filesystem,
    staged_output,
    staging_path_for,
)
from tests.conftest import touch


def test_staging_path_is_in_the_destination_directory_by_default(tmp_path: Path) -> None:
    destination = tmp_path / "library" / "Movie (2024).mkv"

    staging = staging_path_for(destination)

    assert staging.parent == destination.parent


def test_staging_path_is_hidden_and_unique(tmp_path: Path) -> None:
    destination = tmp_path / "Movie.mkv"

    first = staging_path_for(destination)
    second = staging_path_for(destination)

    assert first.name.startswith(".muxarr-")
    assert first.name.endswith(".part")
    assert first != second


def test_staged_output_removes_the_file_on_success(tmp_path: Path) -> None:
    destination = tmp_path / "out.mkv"

    with staged_output(destination) as staging:
        staging.write_bytes(b"data")
        finalise(staging, destination)

    assert destination.read_bytes() == b"data"
    assert not staging.exists()


def test_staged_output_removes_the_file_on_failure(tmp_path: Path) -> None:
    destination = tmp_path / "out.mkv"
    leaked: Path | None = None

    with pytest.raises(RuntimeError), staged_output(destination) as staging:
        leaked = staging
        staging.write_bytes(b"partial")
        raise RuntimeError("mux blew up")

    assert leaked is not None
    assert not leaked.exists()
    assert not destination.exists()


def test_staged_output_creates_missing_directories(tmp_path: Path) -> None:
    destination = tmp_path / "library" / "Show" / "Season 01" / "ep.mkv"

    with staged_output(destination) as staging:
        assert staging.parent.is_dir()
        staging.write_bytes(b"x")
        finalise(staging, destination)

    assert destination.is_file()


def test_finalise_overwrites_an_existing_destination(tmp_path: Path) -> None:
    destination = touch(tmp_path / "out.mkv", b"old")

    with staged_output(destination) as staging:
        staging.write_bytes(b"new")
        finalise(staging, destination)

    assert destination.read_bytes() == b"new"


def test_finalise_requires_the_staged_file(tmp_path: Path) -> None:
    with pytest.raises(PlacementError, match="staged file missing"):
        finalise(tmp_path / "nope.part", tmp_path / "out.mkv")


def test_same_filesystem_is_true_within_one_tree(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()

    assert same_filesystem(tmp_path / "a", tmp_path / "b") is True


def test_same_filesystem_is_false_for_missing_paths(tmp_path: Path) -> None:
    assert same_filesystem(tmp_path / "missing", tmp_path) is False


def test_ensure_free_space_passes_when_there_is_room(tmp_path: Path) -> None:
    ensure_free_space(tmp_path, 1024)


def test_ensure_free_space_raises_when_short(tmp_path: Path) -> None:
    with pytest.raises(InsufficientSpaceError):
        ensure_free_space(tmp_path, 1 << 62)


def test_ensure_free_space_applies_the_headroom_factor(tmp_path: Path) -> None:
    import shutil as _shutil

    free = _shutil.disk_usage(tmp_path).free
    # Exactly the free space is fine at factor 1.0 but not with headroom.
    ensure_free_space(tmp_path, free, factor=1.0)
    with pytest.raises(InsufficientSpaceError):
        ensure_free_space(tmp_path, free, factor=1.5)


def test_copy_attributes_mirrors_permissions(tmp_path: Path) -> None:
    reference = touch(tmp_path / "source.mkv", b"a")
    reference.chmod(0o640)
    target = touch(tmp_path / "out.mkv", b"b")
    target.chmod(0o600)

    copy_attributes(reference, target)

    assert (target.stat().st_mode & 0o777) == 0o640


def test_copy_attributes_tolerates_a_missing_reference(tmp_path: Path) -> None:
    target = touch(tmp_path / "out.mkv", b"b")

    copy_attributes(tmp_path / "gone.mkv", target)

    assert target.is_file()


def test_placement_never_touches_the_source_folder(tmp_path: Path) -> None:
    """The read-only invariant, at the placement layer."""
    source_dir = tmp_path / "downloads"
    source = touch(source_dir / "in.mkv", b"original")
    destination = tmp_path / "library" / "out.mkv"

    before = {p.name: p.read_bytes() for p in source_dir.iterdir()}

    with staged_output(destination) as staging:
        staging.write_bytes(b"muxed")
        finalise(staging, destination)
    copy_attributes(source, destination)

    assert {p.name: p.read_bytes() for p in source_dir.iterdir()} == before
    assert source.is_file()


@pytest.mark.skipif(os.getuid() == 0, reason="running as root makes chown always succeed")
def test_copy_attributes_survives_a_failed_chown(tmp_path: Path) -> None:
    reference = touch(tmp_path / "source.mkv", b"a")
    target = touch(tmp_path / "out.mkv", b"b")

    copy_attributes(reference, target, PlacementPolicy(preserve_ownership=True))

    assert target.is_file()
