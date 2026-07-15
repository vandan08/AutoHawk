from autohawk.db import Database
from autohawk.models import Job


def make_job(url="https://example.com/j/1", title="DevOps Engineer"):
    return Job(
        source="test", company="Acme", title=title, url=url,
        location="Remote", description="Python and Docker required",
    )


def test_upsert_is_idempotent(tmp_path):
    db = Database(tmp_path / "t.db")
    job = make_job()
    assert db.upsert_job(job) is True
    assert db.upsert_job(job) is False  # same URL → same id → no duplicate
    assert db.counts()["total"] == 1


def test_score_and_shortlist_ordering(tmp_path):
    db = Database(tmp_path / "t.db")
    low = make_job(url="https://example.com/a", title="Support Rep")
    high = make_job(url="https://example.com/b", title="Platform Engineer")
    db.upsert_job(low)
    db.upsert_job(high)
    db.save_score(low.id, 30, "keyword")
    db.save_score(high.id, 90, "llm", "strong_apply", ["Python"], [], "Great fit")
    rows = db.shortlist(limit=10)
    assert [r["score"] for r in rows] == [90, 30]
    assert db.shortlist(min_score=50)[0]["id"] == high.id
    assert db.counts()["unscored"] == 0


def test_status_tracking(tmp_path):
    db = Database(tmp_path / "t.db")
    job = make_job()
    db.upsert_job(job)
    db.set_status(job.id, "applied")
    assert db.get_job(job.id)["status"] == "applied"
    assert db.counts()["applied"] == 1
