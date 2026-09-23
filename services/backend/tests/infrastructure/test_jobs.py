"""The queue the API and the worker share.

The shim's correctness rests on two properties: a resubmitted job id must
re-attach rather than queue a second mux, and a claim must be exclusive so two
workers cannot mux the same import concurrently.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from src.application.interfaces.jobs import JobConflictError
from src.application.use_cases.imports.dto import ImportOutcome, ImportRequest, fingerprint
from src.db.session import DBManager
from src.domain.journal import RejectedTrack, RemovedTrack, TrackDetail
from src.infrastructure.jobs.repository import SqlAlchemyJobRepository

REQUEST = ImportRequest(
    app="radarr",
    source_path=Path("/downloads/a.mkv"),
    destination_path=Path("/library/a.mkv"),
)
OTHER_REQUEST = ImportRequest(
    app="radarr",
    source_path=Path("/downloads/b.mkv"),
    destination_path=Path("/library/b.mkv"),
)

FINGERPRINT = fingerprint({"source_path": "/downloads/a.mkv"})
OTHER_FINGERPRINT = fingerprint({"source_path": "/downloads/b.mkv"})

OUTCOME = ImportOutcome(move_status="DeferMove", reason="stub")


@pytest.fixture
def jobs(db: DBManager) -> SqlAlchemyJobRepository:
    return SqlAlchemyJobRepository(db)


class TestCreation:
    async def test_a_new_id_creates_a_job(self, jobs: SqlAlchemyJobRepository) -> None:
        job, created = await jobs.create_or_get("job-1", FINGERPRINT, REQUEST)

        assert created is True
        assert job.id == "job-1"
        assert job.state == "pending"

    async def test_the_same_id_and_request_re_attaches(
        self, jobs: SqlAlchemyJobRepository
    ) -> None:
        first, _ = await jobs.create_or_get("job-1", FINGERPRINT, REQUEST)
        second, created = await jobs.create_or_get("job-1", FINGERPRINT, REQUEST)

        assert created is False
        assert second.id == first.id

    async def test_the_same_id_with_a_different_request_conflicts(
        self, jobs: SqlAlchemyJobRepository
    ) -> None:
        await jobs.create_or_get("job-1", FINGERPRINT, REQUEST)

        with pytest.raises(JobConflictError):
            await jobs.create_or_get("job-1", OTHER_FINGERPRINT, OTHER_REQUEST)

    async def test_the_request_round_trips(self, jobs: SqlAlchemyJobRepository) -> None:
        await jobs.create_or_get("job-1", FINGERPRINT, REQUEST)

        found = await jobs.get("job-1")

        assert found is not None
        assert found.request == REQUEST

    async def test_unknown_id_is_none(self, jobs: SqlAlchemyJobRepository) -> None:
        assert await jobs.get("nope") is None


class TestClaiming:
    async def test_claims_the_oldest_pending_job(self, jobs: SqlAlchemyJobRepository) -> None:
        await jobs.create_or_get("job-1", FINGERPRINT, REQUEST)
        await jobs.create_or_get("job-2", OTHER_FINGERPRINT, OTHER_REQUEST)

        claimed = await jobs.claim_next()

        assert claimed is not None
        assert claimed.id == "job-1"
        assert claimed.state == "running"

    async def test_an_empty_queue_claims_nothing(self, jobs: SqlAlchemyJobRepository) -> None:
        assert await jobs.claim_next() is None

    async def test_a_claimed_job_is_not_claimed_twice(
        self, jobs: SqlAlchemyJobRepository
    ) -> None:
        await jobs.create_or_get("job-1", FINGERPRINT, REQUEST)

        assert await jobs.claim_next() is not None
        assert await jobs.claim_next() is None

    async def test_concurrent_claims_each_get_a_distinct_job(
        self, jobs: SqlAlchemyJobRepository
    ) -> None:
        """Two workers must never mux the same import."""
        await jobs.create_or_get("job-1", FINGERPRINT, REQUEST)
        await jobs.create_or_get("job-2", OTHER_FINGERPRINT, OTHER_REQUEST)

        claimed = await asyncio.gather(*(jobs.claim_next() for _ in range(4)))

        ids = sorted(job.id for job in claimed if job is not None)
        assert ids == ["job-1", "job-2"]


class TestCompletion:
    async def test_succeed_stores_the_outcome_and_history_id(
        self, jobs: SqlAlchemyJobRepository
    ) -> None:
        await jobs.create_or_get("job-1", FINGERPRINT, REQUEST)
        await jobs.succeed("job-1", OUTCOME, 42)

        found = await jobs.get("job-1")

        assert found is not None
        assert found.state == "succeeded"
        assert found.done is True
        assert found.outcome == OUTCOME
        assert found.history_id == 42

    async def test_a_full_outcome_round_trips(self, jobs: SqlAlchemyJobRepository) -> None:
        """The API renders the protocol from this, so every field has to survive."""
        rich = ImportOutcome(
            move_status="RenameRequested",
            reason="embedded 1 external track(s)",
            media_file=Path("/library/a.mkv"),
            extra_files=(Path("/downloads/leftover.srt"),),
            prevent_extra_import=True,
            added_tracks=(TrackDetail(kind="subtitles", label="Russian", language="rus"),),
            rejected_tracks=(RejectedTrack(track="eng.srt", reason="already present"),),
            removed_tracks=(
                RemovedTrack(index=2, kind="audio", language="fre", codec="ac3", reason="no"),
            ),
            duration_ms=1234,
            source_bytes=100,
            output_bytes=120,
        )
        await jobs.create_or_get("job-1", FINGERPRINT, REQUEST)
        await jobs.succeed("job-1", rich, None)

        found = await jobs.get("job-1")

        assert found is not None
        assert found.outcome == rich

    async def test_fail_stores_the_error(self, jobs: SqlAlchemyJobRepository) -> None:
        await jobs.create_or_get("job-1", FINGERPRINT, REQUEST)
        await jobs.fail("job-1", "RuntimeError: boom")

        found = await jobs.get("job-1")

        assert found is not None
        assert found.state == "failed"
        assert found.error == "RuntimeError: boom"


class TestReconciliation:
    async def test_interrupted_jobs_are_failed(self, jobs: SqlAlchemyJobRepository) -> None:
        """A row left running died with its worker; the shim must see an error."""
        await jobs.create_or_get("job-1", FINGERPRINT, REQUEST)
        await jobs.claim_next()

        assert await jobs.fail_running("worker restarted") == 1

        found = await jobs.get("job-1")
        assert found is not None
        assert found.state == "failed"

    async def test_queued_jobs_are_left_alone(self, jobs: SqlAlchemyJobRepository) -> None:
        """Nothing has run them yet, and the starting worker is about to."""
        await jobs.create_or_get("job-1", FINGERPRINT, REQUEST)

        assert await jobs.fail_running("worker restarted") == 0

        found = await jobs.get("job-1")
        assert found is not None
        assert found.state == "pending"

    async def test_finished_jobs_are_left_alone(self, jobs: SqlAlchemyJobRepository) -> None:
        await jobs.create_or_get("job-1", FINGERPRINT, REQUEST)
        await jobs.succeed("job-1", OUTCOME, None)

        assert await jobs.fail_running("worker restarted") == 0

        found = await jobs.get("job-1")
        assert found is not None
        assert found.state == "succeeded"


class TestPruning:
    async def test_fresh_finished_jobs_survive(self, jobs: SqlAlchemyJobRepository) -> None:
        """Evicting a job the shim has not read yet fails a good import."""
        await jobs.create_or_get("job-1", FINGERPRINT, REQUEST)
        await jobs.succeed("job-1", OUTCOME, None)

        assert await jobs.prune(3600) == 0

    async def test_expired_finished_jobs_are_dropped(
        self, jobs: SqlAlchemyJobRepository
    ) -> None:
        await jobs.create_or_get("job-1", FINGERPRINT, REQUEST)
        await jobs.succeed("job-1", OUTCOME, None)

        assert await jobs.prune(-1) == 1
        assert await jobs.get("job-1") is None

    async def test_unfinished_jobs_are_never_pruned(
        self, jobs: SqlAlchemyJobRepository
    ) -> None:
        await jobs.create_or_get("job-1", FINGERPRINT, REQUEST)

        assert await jobs.prune(-1) == 0


class TestCounts:
    async def test_an_empty_queue_reports_every_state(
        self, jobs: SqlAlchemyJobRepository
    ) -> None:
        """A missing key would make the dashboard render a gap, not a zero."""
        assert await jobs.counts_by_state() == {
            "pending": 0,
            "running": 0,
            "succeeded": 0,
            "failed": 0,
        }

    async def test_counts_follow_a_job_through_its_states(
        self, jobs: SqlAlchemyJobRepository
    ) -> None:
        await jobs.create_or_get("job-1", FINGERPRINT, REQUEST)
        assert (await jobs.counts_by_state())["pending"] == 1

        await jobs.claim_next()
        counts = await jobs.counts_by_state()
        assert counts["pending"] == 0
        assert counts["running"] == 1

        await jobs.succeed("job-1", OUTCOME, None)
        counts = await jobs.counts_by_state()
        assert counts["running"] == 0
        assert counts["succeeded"] == 1

    async def test_states_are_counted_independently(
        self, jobs: SqlAlchemyJobRepository
    ) -> None:
        await jobs.create_or_get("job-1", FINGERPRINT, REQUEST)
        await jobs.create_or_get("job-2", OTHER_FINGERPRINT, OTHER_REQUEST)
        await jobs.fail("job-1", "boom")

        assert await jobs.counts_by_state() == {
            "pending": 1,
            "running": 0,
            "succeeded": 0,
            "failed": 1,
        }
