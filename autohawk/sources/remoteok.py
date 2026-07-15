"""RemoteOK public API: https://remoteok.com/api (first element is a legal notice)."""

from __future__ import annotations

from ..models import Job
from ..utils import strip_html
from .http import get_json


def parse_job(raw: dict) -> Job:
    return Job(
        source="remoteok",
        company=raw.get("company", ""),
        title=raw.get("position", "") or raw.get("title", ""),
        url=raw.get("url", ""),
        location=raw.get("location", "") or "Remote",
        description=strip_html(raw.get("description", "")),
        posted_at=(raw.get("date") or "")[:10],
        tags=raw.get("tags", []) or [],
    )


def fetch(cfg: dict | bool | None) -> list[Job]:
    tags = []
    if isinstance(cfg, dict):
        tags = [t.lower() for t in cfg.get("tags", []) or []]
    data = get_json("https://remoteok.com/api")
    jobs: list[Job] = []
    for raw in data:
        if not isinstance(raw, dict) or "position" not in raw:
            continue  # skips the leading legal-notice element
        job = parse_job(raw)
        # RemoteOK tag data is unreliable — accept a match in tags OR title
        if tags and not (
            set(tags) & {t.lower() for t in job.tags}
            or any(t in job.title.lower() for t in tags)
        ):
            continue
        jobs.append(job)
    return jobs
