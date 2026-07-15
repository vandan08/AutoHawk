"""Remotive public API: https://remotive.com/api/remote-jobs"""

from __future__ import annotations

from ..models import Job
from ..utils import strip_html
from .http import get_json


def parse_job(raw: dict) -> Job:
    return Job(
        source="remotive",
        company=raw.get("company_name", ""),
        title=raw.get("title", ""),
        url=raw.get("url", ""),
        location=raw.get("candidate_required_location", "") or "Remote",
        description=strip_html(raw.get("description", "")),
        posted_at=(raw.get("publication_date") or "")[:10],
        tags=raw.get("tags", []) or [],
    )


def fetch(cfg: dict | None) -> list[Job]:
    params: dict = {"limit": 100}
    if isinstance(cfg, dict) and cfg.get("search"):
        params["search"] = cfg["search"]
    data = get_json("https://remotive.com/api/remote-jobs", params=params)
    return [parse_job(raw) for raw in data.get("jobs", [])]
