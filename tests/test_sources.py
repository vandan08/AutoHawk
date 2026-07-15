"""Parser tests against captured API shapes — no network required."""

from autohawk.sources import adzuna, greenhouse, lever, remoteok, remotive


def test_greenhouse_parse():
    raw = {
        "title": "Security Engineer",
        "absolute_url": "https://boards.greenhouse.io/acme/jobs/123",
        "location": {"name": "Remote - India"},
        "content": "&lt;p&gt;Do &lt;b&gt;security&lt;/b&gt; things&lt;/p&gt;",
        "updated_at": "2026-07-01T10:00:00-04:00",
    }
    job = greenhouse.parse_job("acme", raw)
    assert job.company == "acme"
    assert job.location == "Remote - India"
    assert "security things" in job.description
    assert job.posted_at == "2026-07-01"
    assert len(job.id) == 12


def test_lever_parse():
    raw = {
        "text": "Platform Engineer",
        "hostedUrl": "https://jobs.lever.co/acme/abc",
        "categories": {"location": "Bengaluru", "team": "Infra", "commitment": "Full-time"},
        "descriptionPlain": "Kubernetes at scale",
        "createdAt": 1751500800000,
    }
    job = lever.parse_job("acme", raw)
    assert job.title == "Platform Engineer"
    assert job.location == "Bengaluru"
    assert "Infra" in job.tags
    assert job.posted_at.startswith("2025") or job.posted_at.startswith("2026")


def test_remoteok_parse():
    raw = {
        "position": "DevOps Engineer",
        "company": "Acme",
        "url": "https://remoteok.com/remote-jobs/1",
        "description": "<p>CI/CD pipelines</p>",
        "tags": ["devops", "aws"],
        "date": "2026-07-10T00:00:00+00:00",
    }
    job = remoteok.parse_job(raw)
    assert job.title == "DevOps Engineer"
    assert job.location == "Remote"
    assert "CI/CD pipelines" in job.description


def test_remotive_parse():
    raw = {
        "title": "SRE",
        "company_name": "Acme",
        "url": "https://remotive.com/remote-jobs/sre-1",
        "description": "<p>Reliability work</p>",
        "candidate_required_location": "Worldwide",
        "publication_date": "2026-07-12T08:00:00",
        "tags": ["sre"],
    }
    job = remotive.parse_job(raw)
    assert job.company == "Acme"
    assert job.posted_at == "2026-07-12"


def test_adzuna_parse():
    raw = {
        "title": "Cloud Engineer",
        "redirect_url": "https://adzuna.in/details/1",
        "company": {"display_name": "Acme India"},
        "location": {"display_name": "Ahmedabad, Gujarat"},
        "description": "Terraform and AWS",
        "created": "2026-07-14T12:00:00Z",
    }
    job = adzuna.parse_job(raw)
    assert job.company == "Acme India"
    assert job.location == "Ahmedabad, Gujarat"
    assert job.posted_at == "2026-07-14"
