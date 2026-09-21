"""Contract tests for the shell shim.

The shim must exit 0 and print exactly one valid ``[MoveStatus]`` no matter what
the daemon does -- including being unreachable, timing out, or returning HTML.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from tests.test_protocol import ARR_OUTPUT_REGEX

SHIM = Path(__file__).resolve().parent.parent / "scripts" / "muxarr-import.sh"

pytestmark = pytest.mark.skipif(
    shutil.which("curl") is None and shutil.which("wget") is None,
    reason="shim needs curl or wget",
)


class _Handler(BaseHTTPRequestHandler):
    body = b"[MoveStatus] DeferMove\n"
    code = 200
    content_type = "text/plain"
    received: list[dict[str, object]] = []

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        try:
            type(self).received.append(json.loads(raw))
        except json.JSONDecodeError:
            type(self).received.append({"_unparseable": raw.decode("utf-8", "replace")})
        self.send_response(type(self).code)
        self.send_header("Content-Type", type(self).content_type)
        self.end_headers()
        self.wfile.write(type(self).body)

    def log_message(self, *_args: object) -> None:
        return


@pytest.fixture
def daemon() -> Iterator[type[_Handler]]:
    _Handler.body = b"[MoveStatus] DeferMove\n"
    _Handler.code = 200
    _Handler.received = []

    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    _Handler.port = server.server_port  # type: ignore[attr-defined]
    try:
        yield _Handler
    finally:
        server.shutdown()
        server.server_close()


def run_shim(
    url: str,
    *,
    source: str = "/downloads/rel/video.mkv",
    destination: str = "/library/Movie (2024)/Movie (2024).mkv",
    app: str = "radarr",
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = {"PATH": "/usr/bin:/bin:/usr/local/bin", "MUXARR_URL": url, "MUXARR_TIMEOUT": "10"}
    if app == "radarr":
        env |= {
            "Radarr_SourcePath": source,
            "Radarr_DestinationPath": destination,
            "Radarr_Movie_Path": "/library/Movie (2024)",
            "Radarr_TransferMode": "Move",
        }
    elif app == "sonarr":
        env |= {
            "Sonarr_SourcePath": source,
            "Sonarr_DestinationPath": destination,
            "Sonarr_Series_Path": "/library/Show",
            "Sonarr_TransferMode": "HardLinkOrCopy",
            "Sonarr_EpisodeFile_SeasonNumber": "1",
            "Sonarr_EpisodeFile_EpisodeNumbers": "2,3",
        }
    env |= extra_env or {}

    return subprocess.run(
        ["/bin/sh", str(SHIM), source, destination],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
        check=False,
    )


def assert_valid_protocol(result: subprocess.CompletedProcess[str]) -> list[str]:
    assert result.returncode == 0, f"shim must always exit 0, got {result.returncode}"
    lines = result.stdout.splitlines()
    assert lines, "shim must always print something"
    for line in lines:
        assert ARR_OUTPUT_REGEX.match(line), f"*arr would silently ignore: {line!r}"
    statuses = [line for line in lines if line.startswith("[MoveStatus]")]
    assert len(statuses) == 1, f"expected exactly one MoveStatus, got {statuses}"
    return lines


def url_for(daemon: type[_Handler]) -> str:
    return f"http://127.0.0.1:{daemon.port}"  # type: ignore[attr-defined]


def test_happy_path_defer(daemon: type[_Handler]) -> None:
    result = run_shim(url_for(daemon))

    assert assert_valid_protocol(result) == ["[MoveStatus] DeferMove"]


def test_happy_path_rename_requested(daemon: type[_Handler]) -> None:
    daemon.body = (
        b"[MediaFile] /library/Movie (2024)/Movie (2024).mkv\n"
        b"[PreventExtraImport]\n"
        b"[MoveStatus] RenameRequested\n"
    )

    lines = assert_valid_protocol(run_shim(url_for(daemon)))

    assert lines == [
        "[MediaFile] /library/Movie (2024)/Movie (2024).mkv",
        "[PreventExtraImport]",
        "[MoveStatus] RenameRequested",
    ]


def test_daemon_unreachable_defers(tmp_path: Path) -> None:
    # Port 1 is reserved and will refuse immediately.
    result = run_shim("http://127.0.0.1:1")

    assert assert_valid_protocol(result) == ["[MoveStatus] DeferMove"]


def test_http_500_defers(daemon: type[_Handler]) -> None:
    daemon.code = 500
    daemon.body = b"internal server error\n"

    assert assert_valid_protocol(run_shim(url_for(daemon))) == ["[MoveStatus] DeferMove"]


def test_html_error_page_is_not_echoed(daemon: type[_Handler]) -> None:
    """A reverse proxy returning HTML must not leak into *arr's parser."""
    daemon.body = b"<html><body>502 Bad Gateway</body></html>\n"

    assert assert_valid_protocol(run_shim(url_for(daemon))) == ["[MoveStatus] DeferMove"]


def test_response_without_move_status_defers(daemon: type[_Handler]) -> None:
    daemon.body = b"[MediaFile] /library/Movie (2024)/Movie (2024).mkv\n"

    assert assert_valid_protocol(run_shim(url_for(daemon))) == ["[MoveStatus] DeferMove"]


def test_stray_log_lines_are_filtered_out(daemon: type[_Handler]) -> None:
    daemon.body = (
        b"INFO starting mux\n"
        b"[MediaFile] /library/Movie (2024)/Movie (2024).mkv\n"
        b"mkvmerge: progress 100%\n"
        b"[MoveStatus] RenameRequested\n"
    )

    lines = assert_valid_protocol(run_shim(url_for(daemon)))

    assert lines == [
        "[MediaFile] /library/Movie (2024)/Movie (2024).mkv",
        "[MoveStatus] RenameRequested",
    ]


def test_crlf_response_is_normalised(daemon: type[_Handler]) -> None:
    """A trailing \\r would break *arr's end-of-line anchor."""
    daemon.body = b"[MoveStatus] RenameRequested\r\n"

    assert assert_valid_protocol(run_shim(url_for(daemon))) == ["[MoveStatus] RenameRequested"]


def test_empty_response_defers(daemon: type[_Handler]) -> None:
    daemon.body = b""

    assert assert_valid_protocol(run_shim(url_for(daemon))) == ["[MoveStatus] DeferMove"]


def test_no_arr_environment_defers(daemon: type[_Handler]) -> None:
    result = subprocess.run(
        ["/bin/sh", str(SHIM), "/a.mkv", "/b.mkv"],
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "MUXARR_URL": url_for(daemon)},
        timeout=30,
        check=False,
    )

    assert assert_valid_protocol(result) == ["[MoveStatus] DeferMove"]


class TestPayload:
    def test_radarr_payload(self, daemon: type[_Handler]) -> None:
        run_shim(url_for(daemon))

        sent = daemon.received[0]
        assert sent["app"] == "radarr"
        assert sent["library_path"] == "/library/Movie (2024)"
        assert sent["season"] is None
        assert sent["episodes"] == []

    def test_sonarr_payload_carries_episode_numbers(self, daemon: type[_Handler]) -> None:
        run_shim(url_for(daemon), app="sonarr")

        sent = daemon.received[0]
        assert sent["app"] == "sonarr"
        assert sent["season"] == 1
        assert sent["episodes"] == [2, 3]
        assert sent["transfer_mode"] == "HardLinkOrCopy"

    def test_paths_with_quotes_and_backslashes_survive_json_encoding(
        self, daemon: type[_Handler]
    ) -> None:
        nasty = '/downloads/we"ird\\path/video.mkv'

        run_shim(url_for(daemon), source=nasty)

        assert daemon.received[0]["source_path"] == nasty

    def test_cyrillic_paths_survive(self, daemon: type[_Handler]) -> None:
        cyrillic = "/downloads/Надписи/видео.mkv"

        run_shim(url_for(daemon), source=cyrillic)

        assert daemon.received[0]["source_path"] == cyrillic

    def test_malicious_episode_numbers_are_sanitised(self, daemon: type[_Handler]) -> None:
        """Episode numbers are interpolated into JSON, so they must be digits only."""
        run_shim(
            url_for(daemon),
            app="sonarr",
            extra_env={"Sonarr_EpisodeFile_EpisodeNumbers": '2],"app":"evil","x":[3'},
        )

        sent = daemon.received[0]
        assert sent["app"] == "sonarr"
        assert sent["episodes"] == [2, 3]

    def test_malicious_season_is_sanitised(self, daemon: type[_Handler]) -> None:
        run_shim(
            url_for(daemon),
            app="sonarr",
            extra_env={"Sonarr_EpisodeFile_SeasonNumber": '1,"app":"evil"'},
        )

        assert daemon.received[0]["season"] == 1


def test_token_is_sent_when_configured(daemon: type[_Handler]) -> None:
    captured: list[str] = []

    original = _Handler.do_POST

    def spy(self: _Handler) -> None:
        captured.append(self.headers.get("Authorization", ""))
        original(self)

    _Handler.do_POST = spy  # type: ignore[method-assign]
    try:
        run_shim(url_for(daemon), extra_env={"MUXARR_TOKEN": "abc123"})
    finally:
        _Handler.do_POST = original  # type: ignore[method-assign]

    assert captured == ["Bearer abc123"]


def test_shim_has_no_bashisms() -> None:
    """The *arr containers ship dash/busybox sh, not bash."""
    text = SHIM.read_text(encoding="utf-8")

    assert text.startswith("#!/bin/sh")
    for bashism in (r"\[\[", r"\bfunction\s+\w+\s*\(", r"\$\(\(", r"\blocal\b"):
        assert re.search(bashism, text) is None, f"bashism found: {bashism}"
