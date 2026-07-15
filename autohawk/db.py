from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .models import Job

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id          TEXT PRIMARY KEY,
    source      TEXT NOT NULL,
    company     TEXT NOT NULL,
    title       TEXT NOT NULL,
    location    TEXT DEFAULT '',
    url         TEXT NOT NULL,
    description TEXT DEFAULT '',
    tags        TEXT DEFAULT '',
    posted_at   TEXT DEFAULT '',
    fetched_at  TEXT NOT NULL,
    score       INTEGER,
    score_method TEXT,
    recommendation TEXT,
    matched_skills TEXT,
    gaps        TEXT,
    reasoning   TEXT,
    status      TEXT DEFAULT 'new'
);
CREATE INDEX IF NOT EXISTS idx_jobs_score ON jobs (score DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs (status);
"""


def default_db_path() -> str:
    return os.environ.get("AUTOHAWK_DB", "autohawk.db")


class Database:
    def __init__(self, path: str | Path | None = None):
        self.path = str(path or default_db_path())
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)

    def close(self) -> None:
        self.conn.close()

    # --- writes ---------------------------------------------------------------

    def upsert_job(self, job: Job) -> bool:
        """Insert a job if unseen. Returns True when it was newly inserted."""
        cur = self.conn.execute(
            """
            INSERT INTO jobs (id, source, company, title, location, url,
                              description, tags, posted_at, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO NOTHING
            """,
            (
                job.id,
                job.source,
                job.company,
                job.title,
                job.location,
                job.url,
                job.description,
                ",".join(job.tags),
                job.posted_at,
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
            ),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def save_score(
        self,
        job_id: str,
        score: int,
        method: str,
        recommendation: str = "",
        matched_skills: list[str] | None = None,
        gaps: list[str] | None = None,
        reasoning: str = "",
    ) -> None:
        self.conn.execute(
            """
            UPDATE jobs SET score=?, score_method=?, recommendation=?,
                            matched_skills=?, gaps=?, reasoning=?, status='scored'
            WHERE id=?
            """,
            (
                score,
                method,
                recommendation,
                ", ".join(matched_skills or []),
                ", ".join(gaps or []),
                reasoning,
                job_id,
            ),
        )
        self.conn.commit()

    def set_status(self, job_id: str, status: str) -> None:
        self.conn.execute("UPDATE jobs SET status=? WHERE id=?", (status, job_id))
        self.conn.commit()

    # --- reads ----------------------------------------------------------------

    def get_job(self, job_id: str) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()

    def unscored_jobs(self, limit: int | None = None) -> list[sqlite3.Row]:
        sql = "SELECT * FROM jobs WHERE score IS NULL ORDER BY fetched_at DESC"
        if limit:
            sql += f" LIMIT {int(limit)}"
        return self.conn.execute(sql).fetchall()

    def shortlist(self, limit: int = 20, min_score: int = 0) -> list[sqlite3.Row]:
        return self.conn.execute(
            """
            SELECT * FROM jobs
            WHERE score IS NOT NULL AND score >= ? AND status != 'archived'
            ORDER BY score DESC LIMIT ?
            """,
            (min_score, limit),
        ).fetchall()

    def counts(self) -> dict[str, int]:
        row = self.conn.execute(
            """
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN score IS NULL THEN 1 ELSE 0 END) AS unscored,
                   SUM(CASE WHEN score IS NOT NULL THEN 1 ELSE 0 END) AS scored,
                   SUM(CASE WHEN status = 'applied' THEN 1 ELSE 0 END) AS applied
            FROM jobs
            """
        ).fetchone()
        return {k: row[k] or 0 for k in row.keys()}
