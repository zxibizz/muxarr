from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.api.protocol import DEFER, render, render_text
from src.application.use_cases.imports.dto import ImportOutcome

# Copied verbatim from Radarr/Sonarr src/NzbDrone.Core/MediaFiles/ScriptImportDecider.cs,
# with .NET's (?<name>...) rewritten as Python's (?P<name>...). Nothing else changed.
# A line that fails this regex is SILENTLY IGNORED by *arr, and a missing
# [MoveStatus] defaults to MoveComplete -- i.e. "the file was moved" when it wasn't.
ARR_OUTPUT_REGEX = re.compile(
    r"^(?:\[(?:(?P<mediaFile>MediaFile)|(?P<extraFile>ExtraFile))\]\s?(?P<fileName>.+)"
    r"|(?P<preventExtraImport>\[PreventExtraImport\])"
    r"|\[MoveStatus\]\s?(?:(?P<deferMove>DeferMove)|(?P<moveComplete>MoveComplete)"
    r"|(?P<renameRequested>RenameRequested)))$"
)


def deferred(reason: str = "nothing to do") -> ImportOutcome:
    return ImportOutcome(move_status="DeferMove", reason=reason)


def muxed(tmp_path: Path, **overrides: object) -> ImportOutcome:
    base: dict[str, object] = {
        "move_status": "RenameRequested",
        "reason": "embedded 1 external track(s)",
        "media_file": tmp_path / "Movie (2024).mkv",
        "prevent_extra_import": True,
    }
    base.update(overrides)
    return ImportOutcome(**base)  # type: ignore[arg-type]


def test_defer_renders_exactly_one_line() -> None:
    assert render(deferred()) == [DEFER]


def test_defer_never_emits_a_media_file_line(tmp_path: Path) -> None:
    """A MediaFile line alongside DeferMove would mislead *arr's bookkeeping."""
    outcome = ImportOutcome(
        move_status="DeferMove",
        reason="mux failed",
        media_file=tmp_path / "stale.mkv",
        prevent_extra_import=True,
    )

    assert render(outcome) == [DEFER]


def test_successful_mux_line_order(tmp_path: Path) -> None:
    lines = render(muxed(tmp_path, extra_files=(tmp_path / "leftover.srt",)))

    assert lines == [
        f"[MediaFile] {tmp_path / 'Movie (2024).mkv'}",
        f"[ExtraFile] {tmp_path / 'leftover.srt'}",
        "[PreventExtraImport]",
        "[MoveStatus] RenameRequested",
    ]


def test_move_status_is_always_last(tmp_path: Path) -> None:
    lines = render(muxed(tmp_path))

    assert lines[-1].startswith("[MoveStatus]")


@pytest.mark.parametrize(
    "outcome_factory",
    [
        lambda p: deferred(),
        lambda p: muxed(p),
        lambda p: muxed(p, move_status="MoveComplete"),
        lambda p: muxed(p, prevent_extra_import=False),
        lambda p: muxed(p, extra_files=(p / "a.srt", p / "b.srt")),
        lambda p: muxed(p, media_file=p / "name with spaces (2024) [1080p].mkv"),
        lambda p: muxed(p, media_file=p / "Надписи" / "Фильм.mkv"),
        lambda p: muxed(p, media_file=p / "Movie - S01E02-E03.mkv"),
    ],
)
def test_every_rendered_line_matches_arrs_regex(outcome_factory: object, tmp_path: Path) -> None:
    lines = render(outcome_factory(tmp_path))  # type: ignore[operator]

    assert lines, "render must never produce an empty result"
    for line in lines:
        assert ARR_OUTPUT_REGEX.match(line), f"*arr would silently ignore: {line!r}"


def test_rendered_text_is_newline_terminated_and_not_crlf(tmp_path: Path) -> None:
    text = render_text(muxed(tmp_path))

    assert text.endswith("\n")
    assert "\r" not in text


def test_every_line_of_rendered_text_matches_after_splitting(tmp_path: Path) -> None:
    """Guards the exact bytes the shim will echo, not just the list form."""
    text = render_text(muxed(tmp_path, extra_files=(tmp_path / "x.srt",)))

    for line in text.splitlines():
        assert ARR_OUTPUT_REGEX.match(line), f"*arr would silently ignore: {line!r}"


def test_regex_rejects_a_trailing_carriage_return() -> None:
    """Proves the CRLF concern is real rather than theoretical."""
    assert ARR_OUTPUT_REGEX.match("[MoveStatus] DeferMove") is not None
    assert ARR_OUTPUT_REGEX.match("[MoveStatus] DeferMove\r") is None


def test_regex_rejects_unknown_status() -> None:
    assert ARR_OUTPUT_REGEX.match("[MoveStatus] Whatever") is None
