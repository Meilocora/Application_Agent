"""Tests for the SQLite storage.

Every test gets its own empty database in a temporary folder (fixture `isolated_db`),
so the tests never touch data/jobs.db and can't influence each other.
"""

import pytest

from application_agent import storage
from application_agent.models import JobMatch, JobPosting, JobStatus, ScoredJob, TravelMode
from application_agent.storage import load_jobs, save_jobs, set_status


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Point the storage module to a fresh database file for each test.

    tmp_path:    a new, empty folder per test, created by pytest (and cleaned up later).
    monkeypatch: replaces a value for the duration of one test, then restores it.
    autouse:     applies to every test in this file without being named as a parameter -
                 no test can forget it and accidentally write to the real database.
    """
    db_path = tmp_path / "jobs.db"
    # Patch storage.DB_PATH, not config.DB_PATH: `from config import DB_PATH` made a copy
    # of the name inside the storage module, and that copy is what _connect() reads.
    monkeypatch.setattr(storage, "DB_PATH", db_path)
    return db_path


# freeze_time comes from conftest.py. It is needed here because two saves in one test usually
# happen within the same second - without it, found_at (first save) and updated_at (second
# save) couldn't be told apart.


def scored_job(job_id: str = "job-1", score: int = 70, **job_fields) -> ScoredJob:
    """A complete ScoredJob with sensible defaults - tests only set what matters to them."""
    job = JobPosting(
        id=job_id,
        title="Werkstudent Python",
        company="Example GmbH",
        url=f"https://www.arbeitsagentur.de/jobsuche/jobdetail/{job_id}",
        **job_fields,
    )
    match = JobMatch(
        score=score,
        verdict="good",
        fits_employment_type=True,
        summary="Fits well.",
        matching_skills=["Python"],
        missing_skills=[],
        selling_points=["Built an agent"],
        red_flags=[],
    )
    return ScoredJob(job=job, match=match, commute_minutes={TravelMode.TRANSIT: 25})


# ---------------------------------------------------------------------------
# Saving and loading
# ---------------------------------------------------------------------------


def test_empty_database_has_no_jobs():
    assert load_jobs() == []


def test_saved_job_comes_back_unchanged():
    original = scored_job(application_url="https://jobs.example.com/1", description="Full text")

    save_jobs([original])
    [stored] = load_jobs()  # unpacking also checks that there is exactly one

    # The whole object survives the trip to JSON and back - including nested
    # models, the enum keys of commute_minutes and the application link.
    assert stored.scored == original


def test_new_job_starts_as_new_with_found_at(freeze_time):
    freeze_time(storage, "2026-10-01T08:00:00")

    save_jobs([scored_job()])

    [stored] = load_jobs()
    assert stored.status == JobStatus.NEW
    assert stored.found_at == "2026-10-01T08:00:00"


def test_jobs_are_sorted_by_score_best_first():
    save_jobs([scored_job("low", score=20), scored_job("high", score=90), scored_job("mid", score=55)])

    assert [stored.scored.job.id for stored in load_jobs()] == ["high", "mid", "low"]


def test_saving_nothing_is_fine():
    save_jobs([])
    assert load_jobs() == []


def test_database_file_and_folder_are_created(isolated_db, monkeypatch):
    # A fixture can also be requested by name to get its return value - here the db path.
    nested = isolated_db.parent / "does" / "not" / "exist" / "jobs.db"
    monkeypatch.setattr(storage, "DB_PATH", nested)

    save_jobs([scored_job()])

    assert nested.exists()


# ---------------------------------------------------------------------------
# Loading by id
# ---------------------------------------------------------------------------


def test_load_by_ids_returns_only_those():
    save_jobs([scored_job("a"), scored_job("b"), scored_job("c")])

    ids = {stored.scored.job.id for stored in load_jobs(["a", "c"])}

    assert ids == {"a", "c"}


def test_load_by_ids_ignores_unknown_ids():
    save_jobs([scored_job("a")])

    assert [stored.scored.job.id for stored in load_jobs(["a", "unknown"])] == ["a"]


def test_load_with_empty_id_list_returns_nothing():
    # [] means "none of them" - not "all" like None does.
    save_jobs([scored_job("a")])

    assert load_jobs([]) == []


def test_ids_are_passed_as_data_not_as_sql():
    # If ids were pasted into the SQL text, this "id" would turn the query into
    # "... WHERE id IN ('x' OR '1'='1')" and return every row (SQL injection).
    # The ? placeholders in load_jobs prevent that.
    save_jobs([scored_job("a")])

    assert load_jobs(["x' OR '1'='1"]) == []


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", list(JobStatus))
def test_every_status_can_be_set_and_read(status):
    save_jobs([scored_job("a")])

    assert set_status("a", status) is True
    assert load_jobs()[0].status == status


def test_set_status_of_unknown_id_returns_false():
    save_jobs([scored_job("a")])

    assert set_status("unknown", JobStatus.APPLIED) is False
    assert load_jobs()[0].status == JobStatus.NEW  # nothing else was touched


def test_set_status_changes_only_that_job():
    save_jobs([scored_job("a"), scored_job("b")])

    set_status("a", JobStatus.APPLIED)

    statuses = {stored.scored.job.id: stored.status for stored in load_jobs()}
    assert statuses == {"a": JobStatus.APPLIED, "b": JobStatus.NEW}


# ---------------------------------------------------------------------------
# Saving a job that is already stored - the most important rule of this module
# ---------------------------------------------------------------------------


def test_saving_again_updates_the_assessment_but_keeps_user_data(freeze_time):
    freeze_time(storage, "2026-10-01T08:00:00")
    save_jobs([scored_job("a", score=60)])
    set_status("a", JobStatus.APPLIED)

    # A later search run finds the same posting again and stores a new assessment.
    freeze_time(storage, "2026-10-05T09:30:00")
    save_jobs([scored_job("a", score=85, application_url="https://jobs.example.com/a")])

    [stored] = load_jobs()
    # Updated: everything that comes from the search ...
    assert stored.scored.match.score == 85
    assert stored.scored.job.application_url == "https://jobs.example.com/a"
    # ... kept: everything that belongs to the user.
    assert stored.status == JobStatus.APPLIED
    assert stored.found_at == "2026-10-01T08:00:00"


def test_saving_again_does_not_create_a_duplicate():
    save_jobs([scored_job("a")])
    save_jobs([scored_job("a")])

    assert len(load_jobs()) == 1
