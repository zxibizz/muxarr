"""Unit tests for the in-memory job registry.

The shim's correctness rests on two properties here: a resubmitted job id must
re-attach rather than queue a second mux, and a waiter must be woken the moment a
job settles rather than on its next poll.
"""

from __future__ import annotations

import asyncio

import pytest

from muxarr.jobs import Job, JobConflictError, JobStore, fingerprint
from muxarr.pipeline import ImportOutcome

OUTCOME = ImportOutcome(move_status="DeferMove", reason="stub")

FINGERPRINT = fingerprint({"source_path": "/downloads/a.mkv"})
OTHER_FINGERPRINT = fingerprint({"source_path": "/downloads/b.mkv"})


async def _wait(store: JobStore, timeout: float) -> Job | None:
    """Wait on job-1, with a hard ceiling so a missed wakeup fails fast."""
    return await asyncio.wait_for(store.wait("job-1", timeout), timeout=5)


class TestCreation:
    def test_a_new_id_creates_a_job(self) -> None:
        job, created = JobStore().create_or_get("job-1", FINGERPRINT)

        assert created is True
        assert job.state == "pending"

    def test_the_same_id_returns_the_same_job(self) -> None:
        store = JobStore()
        first, _ = store.create_or_get("job-1", FINGERPRINT)

        second, created = store.create_or_get("job-1", FINGERPRINT)

        assert created is False
        assert second is first

    def test_the_same_id_for_a_different_import_is_rejected(self) -> None:
        store = JobStore()
        store.create_or_get("job-1", FINGERPRINT)

        with pytest.raises(JobConflictError):
            store.create_or_get("job-1", OTHER_FINGERPRINT)

    def test_unknown_ids_read_as_none(self) -> None:
        assert JobStore().get("nope") is None


class TestTransitions:
    def test_success_carries_the_outcome_and_history_row(self) -> None:
        store = JobStore()
        store.create_or_get("job-1", FINGERPRINT)

        store.start("job-1")
        store.succeed("job-1", OUTCOME, 42)

        job = store.get("job-1")
        assert job is not None
        assert job.state == "succeeded"
        assert job.outcome is OUTCOME
        assert job.history_id == 42
        assert job.done is True

    def test_failure_carries_the_error(self) -> None:
        store = JobStore()
        store.create_or_get("job-1", FINGERPRINT)

        store.fail("job-1", "mkvmerge exploded")

        job = store.get("job-1")
        assert job is not None
        assert job.state == "failed"
        assert job.error == "mkvmerge exploded"

    def test_transitioning_an_unknown_job_is_a_no_op(self) -> None:
        JobStore().succeed("nope", OUTCOME, None)


class TestWait:
    def test_waiting_on_an_unknown_job_returns_none(self) -> None:
        assert asyncio.run(JobStore().wait("nope", 0.1)) is None

    def test_an_already_finished_job_returns_immediately(self) -> None:
        store = JobStore()
        store.create_or_get("job-1", FINGERPRINT)
        store.succeed("job-1", OUTCOME, None)

        job = asyncio.run(_wait(store, 30))

        assert job is not None
        assert job.state == "succeeded"

    def test_a_waiter_wakes_as_soon_as_the_job_settles(self) -> None:
        store = JobStore()
        store.create_or_get("job-1", FINGERPRINT)

        async def scenario() -> Job | None:
            async def finish_shortly() -> None:
                await asyncio.sleep(0.05)
                store.succeed("job-1", OUTCOME, None)

            async with asyncio.TaskGroup() as group:
                group.create_task(finish_shortly())
                # Would block for the full 30s if the wakeup were missed.
                waiter = group.create_task(_wait(store, 30))
            return waiter.result()

        job = asyncio.run(scenario())
        assert job is not None
        assert job.state == "succeeded"

    def test_an_intermediate_transition_does_not_end_the_wait(self) -> None:
        """'running' is not terminal; a waiter must keep waiting through it."""
        store = JobStore()
        store.create_or_get("job-1", FINGERPRINT)

        async def scenario() -> Job | None:
            async def progress() -> None:
                await asyncio.sleep(0.02)
                store.start("job-1")
                await asyncio.sleep(0.02)
                store.succeed("job-1", OUTCOME, None)

            async with asyncio.TaskGroup() as group:
                group.create_task(progress())
                waiter = group.create_task(_wait(store, 30))
            return waiter.result()

        job = asyncio.run(scenario())
        assert job is not None
        assert job.state == "succeeded"

    def test_a_still_running_job_is_returned_when_the_wait_expires(self) -> None:
        store = JobStore()
        store.create_or_get("job-1", FINGERPRINT)
        store.start("job-1")

        job = asyncio.run(store.wait("job-1", 0.05))

        assert job is not None
        assert job.state == "running"

    def test_a_zero_wait_polls_without_blocking(self) -> None:
        store = JobStore()
        store.create_or_get("job-1", FINGERPRINT)

        job = asyncio.run(_wait(store, 0))

        assert job is not None
        assert job.state == "pending"


class TestEviction:
    def test_finished_jobs_expire(self) -> None:
        store = JobStore(ttl_seconds=0)
        store.create_or_get("job-1", FINGERPRINT)
        store.succeed("job-1", OUTCOME, None)

        assert store.get("job-1") is None

    def test_unfinished_jobs_never_expire(self) -> None:
        """Evicting a running mux would make the shim fail a healthy import."""
        store = JobStore(ttl_seconds=0)
        store.create_or_get("job-1", FINGERPRINT)
        store.start("job-1")

        assert store.get("job-1") is not None

    def test_the_oldest_finished_jobs_go_first_when_over_capacity(self) -> None:
        store = JobStore(max_jobs=2)
        for index in range(4):
            job_id = f"job-{index}"
            store.create_or_get(job_id, FINGERPRINT)
            store.succeed(job_id, OUTCOME, None)

        store.create_or_get("job-fresh", FINGERPRINT)

        assert store.get("job-0") is None
        assert store.get("job-3") is not None
        assert store.get("job-fresh") is not None
