"""Digest content + recency query — no SMTP or network required."""

from datetime import datetime, timedelta, timezone

from autohawk.db import Database
from autohawk.digest import build_digest, smtp_configured
from autohawk.models import Job


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def make_job(url: str, title: str = "DevOps Engineer") -> Job:
    return Job(source="test", company="Acme", title=title, url=url,
               location="Remote", description="Python and Docker")


def test_recent_scored_filters_by_fetch_time_and_score(tmp_path):
    db = Database(tmp_path / "t.db")
    fresh = make_job("https://example.com/a", "Platform Engineer")
    low = make_job("https://example.com/b", "Support Rep")
    stale = make_job("https://example.com/c", "SRE")
    for j in (fresh, low, stale):
        db.upsert_job(j)
    db.save_score(fresh.id, 90, "llm", "strong_apply", ["Python"], [], "Great fit")
    db.save_score(low.id, 30, "keyword")
    db.save_score(stale.id, 95, "llm")
    # Push one job's fetch time outside the window
    db.conn.execute(
        "UPDATE jobs SET fetched_at=? WHERE id=?",
        (_iso(datetime.now(timezone.utc) - timedelta(days=3)), stale.id),
    )
    db.conn.commit()

    since = _iso(datetime.now(timezone.utc) - timedelta(hours=24))
    rows = db.recent_scored(since, min_score=60, limit=5)
    assert [r["id"] for r in rows] == [fresh.id]


def test_build_digest_contents(tmp_path):
    db = Database(tmp_path / "t.db")
    job = make_job("https://example.com/a", "Platform <Engineer>")
    db.upsert_job(job)
    db.save_score(job.id, 88, "llm", "strong_apply", ["Python"], [], "Solid overlap")
    rows = db.shortlist()

    subject, text, html_body = build_digest(rows)
    assert "1 new match" in subject
    assert "Platform <Engineer>" in subject and "88" in subject
    assert "https://example.com/a" in text
    assert "Platform &lt;Engineer&gt;" in html_body  # escaped in HTML
    assert "Solid overlap" in html_body


def test_smtp_configured_requires_host_and_recipient(monkeypatch):
    monkeypatch.delenv("AUTOHAWK_SMTP_HOST", raising=False)
    monkeypatch.delenv("AUTOHAWK_DIGEST_TO", raising=False)
    assert smtp_configured() is False
    monkeypatch.setenv("AUTOHAWK_SMTP_HOST", "smtp.example.com")
    assert smtp_configured() is False
    monkeypatch.setenv("AUTOHAWK_DIGEST_TO", "me@example.com")
    assert smtp_configured() is True
