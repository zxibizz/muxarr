from __future__ import annotations

import os
from pathlib import Path

import pytest

from src.domain.errors import PathNotAllowedError
from src.domain.paths import PathGuard, is_within, resolve
from tests.conftest import touch


@pytest.fixture
def guard(tmp_path: Path) -> PathGuard:
    (tmp_path / "downloads").mkdir()
    (tmp_path / "library").mkdir()
    return PathGuard.from_roots([tmp_path / "downloads", tmp_path / "library"])


def test_read_inside_a_root_is_allowed(guard: PathGuard, tmp_path: Path) -> None:
    target = touch(tmp_path / "downloads" / "release" / "video.mkv")

    assert guard.check_read(target) == resolve(target)


def test_read_outside_every_root_is_rejected(guard: PathGuard, tmp_path: Path) -> None:
    outside = touch(tmp_path / "elsewhere" / "secret.txt")

    with pytest.raises(PathNotAllowedError, match="outside every configured read root"):
        guard.check_read(outside)


def test_dotdot_traversal_is_rejected(guard: PathGuard, tmp_path: Path) -> None:
    touch(tmp_path / "elsewhere" / "secret.txt")
    traversal = tmp_path / "downloads" / ".." / "elsewhere" / "secret.txt"

    with pytest.raises(PathNotAllowedError):
        guard.check_read(traversal)


def test_absolute_escape_is_rejected(guard: PathGuard) -> None:
    with pytest.raises(PathNotAllowedError):
        guard.check_read(Path("/etc/passwd"))


def test_symlink_escaping_a_root_is_rejected(guard: PathGuard, tmp_path: Path) -> None:
    """A symlink is resolved *before* the containment check, not followed after it."""
    secret = touch(tmp_path / "elsewhere" / "secret.txt")
    link = tmp_path / "downloads" / "innocent.mkv"
    link.symlink_to(secret)

    with pytest.raises(PathNotAllowedError):
        guard.check_read(link)


def test_symlink_staying_inside_a_root_is_allowed(guard: PathGuard, tmp_path: Path) -> None:
    real = touch(tmp_path / "downloads" / "real.mkv")
    link = tmp_path / "downloads" / "link.mkv"
    link.symlink_to(real)

    assert guard.check_read(link) == resolve(real)


def test_symlinked_parent_directory_is_rejected(guard: PathGuard, tmp_path: Path) -> None:
    (tmp_path / "elsewhere").mkdir()
    link_dir = tmp_path / "downloads" / "sneaky"
    link_dir.symlink_to(tmp_path / "elsewhere", target_is_directory=True)

    with pytest.raises(PathNotAllowedError):
        guard.check_read(link_dir / "file.mkv")


def test_a_root_itself_is_readable(guard: PathGuard, tmp_path: Path) -> None:
    assert guard.check_read(tmp_path / "library") == resolve(tmp_path / "library")


class TestDestinations:
    def test_destination_inside_library_is_allowed(
        self, guard: PathGuard, tmp_path: Path
    ) -> None:
        destination = tmp_path / "library" / "Movie (2024)" / "Movie (2024).mkv"

        assert guard.check_destination(destination) == resolve(destination)

    def test_destination_need_not_exist_yet(self, guard: PathGuard, tmp_path: Path) -> None:
        destination = tmp_path / "library" / "brand" / "new" / "file.mkv"

        assert guard.check_destination(destination) == resolve(destination)

    def test_destination_outside_roots_is_rejected(
        self, guard: PathGuard, tmp_path: Path
    ) -> None:
        with pytest.raises(PathNotAllowedError, match="destination"):
            guard.check_destination(tmp_path / "elsewhere" / "out.mkv")

    def test_destination_may_not_be_a_root_itself(
        self, guard: PathGuard, tmp_path: Path
    ) -> None:
        with pytest.raises(PathNotAllowedError, match="is a configured root itself"):
            guard.check_destination(tmp_path / "library")


class TestWrites:
    def test_write_beside_the_destination_is_allowed(
        self, guard: PathGuard, tmp_path: Path
    ) -> None:
        destination = tmp_path / "library" / "Movie" / "Movie.mkv"
        staging = destination.parent / ".muxarr-123-Movie.mkv.part"

        assert guard.check_write(staging, destination) == resolve(staging)

    def test_write_elsewhere_in_the_library_is_rejected(
        self, guard: PathGuard, tmp_path: Path
    ) -> None:
        """Containment is the destination's own directory, not the whole library."""
        destination = tmp_path / "library" / "Movie" / "Movie.mkv"
        stray = tmp_path / "library" / "Other" / "file.mkv"

        with pytest.raises(PathNotAllowedError, match="outside the write root"):
            guard.check_write(stray, destination)

    def test_write_into_the_download_folder_is_rejected(
        self, guard: PathGuard, tmp_path: Path
    ) -> None:
        """The read-only source invariant, enforced at the path layer."""
        destination = tmp_path / "library" / "Movie" / "Movie.mkv"
        source_side = tmp_path / "downloads" / "release" / "video.mkv"

        with pytest.raises(PathNotAllowedError, match="outside the write root"):
            guard.check_write(source_side, destination)

    def test_write_via_symlink_out_of_the_write_root_is_rejected(
        self, guard: PathGuard, tmp_path: Path
    ) -> None:
        destination = tmp_path / "library" / "Movie" / "Movie.mkv"
        destination.parent.mkdir(parents=True)
        (tmp_path / "elsewhere").mkdir()
        link = destination.parent / "escape"
        link.symlink_to(tmp_path / "elsewhere", target_is_directory=True)

        with pytest.raises(PathNotAllowedError):
            guard.check_write(link / "out.mkv", destination)


def test_is_within_handles_identical_paths(tmp_path: Path) -> None:
    assert is_within(resolve(tmp_path), resolve(tmp_path)) is True


def test_is_within_rejects_sibling_prefix_collision(tmp_path: Path) -> None:
    """/library-backup must not count as being inside /library."""
    (tmp_path / "library").mkdir()
    (tmp_path / "library-backup").mkdir()

    assert is_within(resolve(tmp_path / "library-backup"), resolve(tmp_path / "library")) is False


@pytest.mark.skipif(os.name == "nt", reason="POSIX path semantics")
def test_roots_are_resolved_so_macos_private_var_matches(tmp_path: Path) -> None:
    """On macOS /var is a symlink to /private/var; roots must resolve too."""
    guard = PathGuard.from_roots([tmp_path])
    assert guard.check_read(tmp_path / "file.mkv") == resolve(tmp_path / "file.mkv")
