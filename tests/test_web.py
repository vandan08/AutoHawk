"""Dashboard rendering — pure functions, no server or network required."""

from autohawk.db import Database
from autohawk.models import Job
from autohawk.web import render_dashboard, render_job


def seeded_db(tmp_path):
    db = Database(tmp_path / "t.db")
    job = Job(
        source="test", company="Acme <Corp>", title="Platform Engineer",
        url="https://example.com/a", location="Remote",
        description="Kubernetes & Terraform at scale",
    )
    db.upsert_job(job)
    db.save_score(job.id, 85, "llm", "apply", ["Kubernetes"], ["Go"], "Strong infra overlap")
    return db, job


def test_dashboard_lists_jobs_and_escapes_html(tmp_path):
    db, job = seeded_db(tmp_path)
    page = render_dashboard(db.counts(), db.shortlist(), {"running": False, "message": ""})
    assert "Platform Engineer" in page
    assert "Acme &lt;Corp&gt;" in page          # escaped
    assert f"/job/{job.id}" in page             # links to detail
    assert "85" in page
    assert "worker-msg" not in page             # no poll banner when idle


def test_dashboard_shows_worker_banner_and_poll_script(tmp_path):
    db, _ = seeded_db(tmp_path)
    page = render_dashboard(
        db.counts(), db.shortlist(), {"running": True, "message": "Scoring 3/10"}
    )
    assert "Scoring 3/10" in page
    assert "/api/progress" in page              # poll script included while running


def test_job_detail_renders_scoring_and_actions(tmp_path):
    db, job = seeded_db(tmp_path)
    page = render_job(db.get_job(job.id))
    assert "Strong infra overlap" in page
    assert "Kubernetes" in page and "Go" in page
    assert f"/job/{job.id}/status" in page      # status buttons
    assert f"/job/{job.id}/letter" in page      # letter button
    assert "https://example.com/a" in page


def test_job_detail_shows_letter_and_error(tmp_path):
    db, job = seeded_db(tmp_path)
    page = render_job(db.get_job(job.id), letter_text="Dear team,", error="LLM unavailable")
    assert "Dear team," in page
    assert "LLM unavailable" in page
