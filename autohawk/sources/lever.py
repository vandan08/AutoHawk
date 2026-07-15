"""Lever public postings API: https://api.lever.co/v0/postings/{company}?mode=json"""

from __future__ import annotations

from datetime import datetime, timezone

from ..models import Job
from .http import get_json


def parse_job(company: str, raw: dict) -> Job:
    created_ms = raw.get("createdAt")
    posted = (
        datetime.fromtimestamp(created_ms / 1000, tz=timezone.utc).date().isoformat()
        if created_ms
        else ""
    )
    cats = raw.get("categories") or {}
    return Job(
        source="lever",
        company=company,
        title=raw.get("text", ""),
        url=raw.get("hostedUrl", ""),
        location=cats.get("location", ""),
        description=raw.get("descriptionPlain", ""),
        posted_at=posted,
        tags=[t for t in (cats.get("team"), cats.get("commitment")) if t],
    )


def fetch(companies: list[str]) -> list[Job]:
    jobs: list[Job] = []
    for company in companies or []:
        data = get_json(f"https://api.lever.co/v0/postings/{company}", params={"mode": "json"})
        jobs.extend(parse_job(company, raw) for raw in data)
    return jobs
