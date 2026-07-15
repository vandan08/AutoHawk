"""Greenhouse public board API: https://boards-api.greenhouse.io/v1/boards/{board}/jobs"""

from __future__ import annotations

from ..models import Job
from ..utils import strip_html
from .http import get_json


def parse_job(board: str, raw: dict) -> Job:
    return Job(
        source="greenhouse",
        company=board,
        title=raw.get("title", ""),
        url=raw.get("absolute_url", ""),
        location=(raw.get("location") or {}).get("name", ""),
        description=strip_html(raw.get("content", "")),
        posted_at=(raw.get("updated_at") or "")[:10],
    )


def fetch(boards: list[str]) -> list[Job]:
    jobs: list[Job] = []
    for board in boards or []:
        data = get_json(
            f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs",
            params={"content": "true"},
        )
        jobs.extend(parse_job(board, raw) for raw in data.get("jobs", []))
    return jobs
