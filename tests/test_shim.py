"""Contract tests for the shell shim.

The shim queues a job with the daemon and long-polls for the outcome. Two rules
are load-bearing:

* before anything is queued, every failure ends in ``[MoveStatus] DeferMove`` and
  exit 0, so *arr just imports the file itself;
* after a job is queued, a lost or failed result exits non-zero, because a mux
  may still be in flight and a native import would race it.
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
from urllib.parse import urlparse

import pytest

from tests.test_protocol import ARR_OUTPUT_REGEX

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
SHIMS = {
    "radarr": SCRIPTS / "muxarr-import-radarr.sh",
    "sonarr": SCRIPTS / "muxarr-import-sonarr.sh",
}

DONE_DEFER = b"[MuxarrState] done\n[MoveStatus] DeferMove\n"
RUNNING = b"[MuxarrState] running\n"

pytestmark = pytest.mark.skipif(
    shutil.which("curl") is None and shutil.which("wget") is None,
    reason="shim needs curl or wget",
)


class _Handler(BaseHTTPRequestHandler):
    """A daemon stub whose poll replies are scripted per test."""

    submit_code = 202
    # None means "echo the submitted job id back", as the real daemon does.
    submit_body: bytes | None = None
    # Consumed one per poll; the final entry repeats for every poll after it.
    polls: list[tuple[int, bytes]] = [(200, DONE_DEFER)]
    received: list[dict[str, object]] = []
    polled: list[str] = []

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            body = {"_unparseable": raw.decode("utf-8", "replace")}
        type(self).received.append(body)

        reply = type(self).submit_body
        if reply is None:
            job_id = body.get("job_id", "") if isinstance(body, dict) else ""
            reply = json.dumps({"id": job_id, "state": "pending"}).encode()
        self._respond(type(self).submit_code, reply, "application/json")

    def do_GET(self) -> None:  # noqa: N802
        index = len(type(self).polled)
        type(self).polled.append(self.path)
        code, body = type(self).polls[min(index, len(type(self).polls) - 1)]
        self._respond(code, body, "text/plain")

    def _respond(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args: object) -> None:
        return


@pytest.fixture
def daemon() -> Iterator[type[_Handler]]:
    _Handler.submit_code = 202
    _Handler.submit_body = None
    _Handler.polls = [(200, DONE_DEFER)]
    _Handler.received = []
    _Handler.polled = []

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
    env = {
        "PATH": "/usr/bin:/bin:/usr/local/bin",
        "MUXARR_URL": url,
        "MUXARR_TIMEOUT": "30",
        # Kept small so retry and back-off paths run in test time.
        "MUXARR_POLL_WAIT": "1",
        "MUXARR_POLL_INTERVAL": "1",
        "MUXARR_MAX_RETRIES": "2",
    }
    if app == "radarr":
        env |= {"Radarr_TransferMode": "Move"}
    elif app == "sonarr":
        env |= {"Sonarr_TransferMode": "HardLinkOrCopy"}
    env |= extra_env or {}

    return subprocess.run(
        ["/bin/sh", str(SHIMS[app]), source, destination],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
        check=False,
    )


def assert_valid_protocol(result: subprocess.CompletedProcess[str]) -> list[str]:
    assert result.returncode == 0, f"expected a successful exit, got {result.returncode}"
    lines = result.stdout.splitlines()
    assert lines, "shim must always print something when it exits 0"
    for line in lines:
        assert ARR_OUTPUT_REGEX.match(line), f"*arr would silently ignore: {line!r}"
    statuses = [line for line in lines if line.startswith("[MoveStatus]")]
    assert len(statuses) == 1, f"expected exactly one MoveStatus, got {statuses}"
    return lines


def assert_failed_import(result: subprocess.CompletedProcess[str]) -> None:
    """*arr fails the import on a non-zero exit, and reads nothing from stdout."""
    assert result.returncode != 0, "expected a non-zero exit to fail the import"
    assert result.stdout.strip() == "", f"nothing should be printed: {result.stdout!r}"


def url_for(daemon: type[_Handler]) -> str:
    return f"http://127.0.0.1:{daemon.port}"  # type: ignore[attr-defined]



def test_happy_path_defer(daemon: type[_Handler]) -> None:
    result = run_shim(url_for(daemon))

    assert assert_valid_protocol(result) == ["[MoveStatus] DeferMove"]


def test_happy_path_rename_requested(daemon: type[_Handler]) -> None:
    daemon.polls = [
        (
            200,
            b"[MuxarrState] done\n"
            b"[MediaFile] /library/Movie (2024)/Movie (2024).mkv\n"
            b"[PreventExtraImport]\n"
            b"[MoveStatus] RenameRequested\n",
        )
    ]

    lines = assert_valid_protocol(run_shim(url_for(daemon)))

    assert lines == [
        "[MediaFile] /library/Movie (2024)/Movie (2024).mkv",
        "[PreventExtraImport]",
        "[MoveStatus] RenameRequested",
    ]


def test_the_state_line_is_never_echoed_to_arr(daemon: type[_Handler]) -> None:
    """*arr would ignore it, but leaking internals into its parser is still wrong."""
    lines = assert_valid_protocol(run_shim(url_for(daemon)))

    assert not any("MuxarrState" in line for line in lines)


class TestWaiting:
    def test_polls_until_the_mux_finishes(self, daemon: type[_Handler]) -> None:
        daemon.polls = [(200, RUNNING), (200, RUNNING), (200, DONE_DEFER)]

        result = run_shim(url_for(daemon))

        assert assert_valid_protocol(result) == ["[MoveStatus] DeferMove"]
        assert len(daemon.polled) == 3

    def test_every_poll_targets_the_submitted_job(self, daemon: type[_Handler]) -> None:
        daemon.polls = [(200, RUNNING), (200, DONE_DEFER)]

        run_shim(url_for(daemon))

        job_id = daemon.received[0]["job_id"]
        assert isinstance(job_id, str)
        assert len(daemon.polled) == 2
        for path in daemon.polled:
            assert urlparse(path).path == f"/v1/jobs/{job_id}/protocol"

    def test_a_transient_poll_failure_is_retried(self, daemon: type[_Handler]) -> None:
        """A dropped reply mid-remux must not lose a mux that is still running."""
        daemon.polls = [
            (502, b"<html>502 Bad Gateway</html>\n"),
            (200, b"\n"),
            (200, DONE_DEFER),
        ]

        result = run_shim(url_for(daemon), extra_env={"MUXARR_MAX_RETRIES": "3"})

        assert assert_valid_protocol(result) == ["[MoveStatus] DeferMove"]
        assert len(daemon.polled) == 3

    def test_a_good_poll_resets_the_retry_budget(self, daemon: type[_Handler]) -> None:
        """Only *consecutive* failures should count towards giving up."""
        daemon.polls = [
            (502, b"<html>502 Bad Gateway</html>\n"),
            (200, RUNNING),
            (502, b"<html>502 Bad Gateway</html>\n"),
            (200, DONE_DEFER),
        ]

        result = run_shim(url_for(daemon))

        assert assert_valid_protocol(result) == ["[MoveStatus] DeferMove"]
        assert len(daemon.polled) == 4

    def test_giving_up_on_an_unreachable_daemon_fails_the_import(
        self, daemon: type[_Handler]
    ) -> None:
        daemon.polls = [(502, b"<html>502 Bad Gateway</html>\n")]

        assert_failed_import(run_shim(url_for(daemon)))

    def test_exceeding_the_deadline_fails_the_import(self, daemon: type[_Handler]) -> None:
        daemon.polls = [(200, RUNNING)]

        assert_failed_import(run_shim(url_for(daemon), extra_env={"MUXARR_TIMEOUT": "0"}))


class TestQueueFailures:
    """Nothing has been queued yet, so *arr can safely import the file itself."""

    def test_daemon_unreachable_defers(self) -> None:
        # Port 1 is reserved and will refuse immediately.
        result = run_shim("http://127.0.0.1:1")

        assert assert_valid_protocol(result) == ["[MoveStatus] DeferMove"]

    def test_rejected_submission_defers(self, daemon: type[_Handler]) -> None:
        daemon.submit_code = 401
        daemon.submit_body = b'{"detail":"invalid or missing token"}'

        assert assert_valid_protocol(run_shim(url_for(daemon))) == ["[MoveStatus] DeferMove"]
        assert daemon.polled == []

    def test_submission_is_retried_before_giving_up(self, daemon: type[_Handler]) -> None:
        daemon.submit_code = 500
        daemon.submit_body = b"internal server error\n"

        assert assert_valid_protocol(run_shim(url_for(daemon))) == ["[MoveStatus] DeferMove"]
        assert len(daemon.received) == 2  # MUXARR_MAX_RETRIES

    def test_html_error_page_is_not_echoed(self, daemon: type[_Handler]) -> None:
        """A reverse proxy returning HTML must not leak into *arr's parser."""
        daemon.submit_body = b"<html><body>502 Bad Gateway</body></html>\n"

        assert assert_valid_protocol(run_shim(url_for(daemon))) == ["[MoveStatus] DeferMove"]


class TestLostJob:
    """A job was queued, so deferring would race a mux that may still be running."""

    def test_a_forgotten_job_fails_the_import(self, daemon: type[_Handler]) -> None:
        daemon.polls = [(200, b"[MuxarrState] unknown\n")]

        assert_failed_import(run_shim(url_for(daemon)))

    def test_a_failed_job_fails_the_import(self, daemon: type[_Handler]) -> None:
        daemon.polls = [(200, b"[MuxarrState] error\n")]

        assert_failed_import(run_shim(url_for(daemon)))

    def test_a_done_job_without_a_move_status_fails_the_import(
        self, daemon: type[_Handler]
    ) -> None:
        daemon.polls = [(200, b"[MuxarrState] done\n[MediaFile] /library/Movie.mkv\n")]

        assert_failed_import(run_shim(url_for(daemon)))


def test_stray_log_lines_are_filtered_out(daemon: type[_Handler]) -> None:
    daemon.polls = [
        (
            200,
            b"[MuxarrState] done\n"
            b"INFO starting mux\n"
            b"[MediaFile] /library/Movie (2024)/Movie (2024).mkv\n"
            b"mkvmerge: progress 100%\n"
            b"[MoveStatus] RenameRequested\n",
        )
    ]

    lines = assert_valid_protocol(run_shim(url_for(daemon)))

    assert lines == [
        "[MediaFile] /library/Movie (2024)/Movie (2024).mkv",
        "[MoveStatus] RenameRequested",
    ]


def test_crlf_response_is_normalised(daemon: type[_Handler]) -> None:
    """A trailing \\r would break *arr's end-of-line anchor."""
    daemon.polls = [(200, b"[MuxarrState] done\r\n[MoveStatus] RenameRequested\r\n")]

    assert assert_valid_protocol(run_shim(url_for(daemon))) == ["[MoveStatus] RenameRequested"]


@pytest.mark.parametrize("app", ["radarr", "sonarr"])
def test_missing_arguments_defer(daemon: type[_Handler], app: str) -> None:
    result = subprocess.run(
        ["/bin/sh", str(SHIMS[app])],
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "MUXARR_URL": url_for(daemon)},
        timeout=30,
        check=False,
    )

    assert assert_valid_protocol(result) == ["[MoveStatus] DeferMove"]
    assert daemon.received == []


class TestPayload:
    def test_radarr_payload(self, daemon: type[_Handler]) -> None:
        run_shim(url_for(daemon))

        sent = daemon.received[0]
        assert sent["app"] == "radarr"
        assert sent["source_path"] == "/downloads/rel/video.mkv"
        assert sent["destination_path"] == "/library/Movie (2024)/Movie (2024).mkv"

    def test_sonarr_payload(self, daemon: type[_Handler]) -> None:
        run_shim(url_for(daemon), app="sonarr")

        sent = daemon.received[0]
        assert sent["app"] == "sonarr"
        assert sent["transfer_mode"] == "HardLinkOrCopy"

    def test_the_job_id_is_acceptable_to_the_daemon(self, daemon: type[_Handler]) -> None:
        run_shim(url_for(daemon))

        job_id = daemon.received[0]["job_id"]
        assert isinstance(job_id, str)
        assert re.fullmatch(r"[A-Za-z0-9._:-]{8,128}", job_id), job_id

    def test_a_retried_submission_reuses_the_job_id(self, daemon: type[_Handler]) -> None:
        """Otherwise a lost reply would queue the same remux twice."""
        daemon.submit_code = 500
        daemon.submit_body = b"internal server error\n"

        run_shim(url_for(daemon))

        assert len({sent["job_id"] for sent in daemon.received}) == 1

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

    def test_a_malicious_transfer_mode_cannot_inject_keys(
        self, daemon: type[_Handler]
    ) -> None:
        run_shim(
            url_for(daemon),
            app="sonarr",
            extra_env={"Sonarr_TransferMode": '","app":"evil'},
        )

        sent = daemon.received[0]
        assert sent["app"] == "sonarr"
        assert sent["transfer_mode"] == '","app":"evil'


def test_token_is_sent_on_both_submit_and_poll(daemon: type[_Handler]) -> None:
    captured: list[str] = []

    original_post = _Handler.do_POST
    original_get = _Handler.do_GET

    def spy_post(self: _Handler) -> None:
        captured.append(self.headers.get("Authorization", ""))
        original_post(self)

    def spy_get(self: _Handler) -> None:
        captured.append(self.headers.get("Authorization", ""))
        original_get(self)

    _Handler.do_POST = spy_post  # type: ignore[method-assign]
    _Handler.do_GET = spy_get  # type: ignore[method-assign]
    try:
        run_shim(url_for(daemon), extra_env={"MUXARR_TOKEN": "abc123"})
    finally:
        _Handler.do_POST = original_post  # type: ignore[method-assign]
        _Handler.do_GET = original_get  # type: ignore[method-assign]

    assert captured == ["Bearer abc123", "Bearer abc123"]


def test_shim_has_no_bashisms() -> None:
    """The *arr containers ship dash/busybox sh, not bash."""
    for shim in SHIMS.values():
        text = shim.read_text(encoding="utf-8")

        assert text.startswith("#!/bin/sh")
        for bashism in (r"\[\[", r"\bfunction\s+\w+\s*\(", r"\blocal\b"):
            assert re.search(bashism, text) is None, f"bashism in {shim.name}: {bashism}"

