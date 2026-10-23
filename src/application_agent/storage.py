"""SQLite storage for assessed postings - the single source of truth for every view (Excel, later a UI).

The full ScoredJob is stored as JSON. The columns next to it are copies of the fields views
sort and filter by, plus the ones that belong to the user alone (status, found_at).
"""

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime

from application_agent.config import DB_PATH
from application_agent.models import JobStatus, ScoredJob

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    score INTEGER NOT NULL,
    url TEXT NOT NULL,
    application_url TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'new',
    found_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    data TEXT NOT NULL
)
"""


# @dataclass generates __init__, __repr__ and __eq__ from the annotated fields below.
# A dataclass instead of a pydantic model: the data is already validated (by
# ScoredJob.model_validate_json), this class only bundles it - no validation needed.
@dataclass
class StoredJob:
    scored: ScoredJob
    status: JobStatus
    found_at: str


def _connect() -> sqlite3.Connection:
    """Opens a connection to the SQLite database, creating it if necessary."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.execute(_SCHEMA)
    return connection


def save_jobs(scored_jobs: list[ScoredJob]) -> None:
    """Insert new postings, refresh known ones. Status and found_at of known postings are kept."""
    now = datetime.now().isoformat(timespec="seconds")
    rows = [
        (s.job.id, s.job.title, s.job.company, s.match.score, s.job.url, s.job.application_url,
         now, now, s.model_dump_json())
        for s in scored_jobs
    ]
    # closing() closes the connection after commit or rollback
    with closing(_connect()) as connection, connection:
        connection.executemany(
            """
            INSERT INTO jobs (id, title, company, score, url, application_url, found_at, updated_at, data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (id) DO UPDATE SET
                title = excluded.title, company = excluded.company, score = excluded.score,
                url = excluded.url, application_url = excluded.application_url,
                updated_at = excluded.updated_at, data = excluded.data
            """,
            rows,
        )


def load_jobs(ids: list[str] | None = None) -> list[StoredJob]:
    """All stored postings (or only those with the given ids), best score first."""
    query = "SELECT data, status, found_at FROM jobs"
    params: list[str] = []
    if ids is not None:
        query += f" WHERE id IN ({', '.join('?' * len(ids))})"
        params = ids
    with closing(_connect()) as connection:
        rows = connection.execute(f"{query} ORDER BY score DESC", params).fetchall()
    return [StoredJob(ScoredJob.model_validate_json(data), JobStatus(status), found_at) for data, status, found_at in rows]


def set_status(job_id: str, status: JobStatus) -> bool:
    """Change the status of a posting. Returns False if the id is unknown."""
    now = datetime.now().isoformat(timespec="seconds")
    with closing(_connect()) as connection, connection:
        cursor = connection.execute(
            "UPDATE jobs SET status = ?, updated_at = ? WHERE id = ?", (status, now, job_id)
        )
    return cursor.rowcount > 0
