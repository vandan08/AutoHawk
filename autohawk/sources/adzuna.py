"""Adzuna search API (needs free ADZUNA_APP_ID / ADZUNA_APP_KEY credentials)."""

from __future__ import annotations

import os

from ..models import Job
from .http import get_json


def parse_job(raw: dict) -> Job:
    return Job(
        source="adzuna",
        company=(raw.get("company") or {}).get("display_name", ""),
        title=raw.get("title", ""),
        url=raw.get("redirect_url", ""),
        location=(raw.get("location") or {}).get("display_name", ""),
        description=raw.get("description", ""),
        posted_at=(raw.get("created") or "")[:10],
    )


def fetch(cfg: dict | None) -> list[Job]:
    app_id = os.environ.get("ADZUNA_APP_ID")
    app_key = os.environ.get("ADZUNA_APP_KEY")
    if not app_id or not app_key:
        raise RuntimeError(
            "Adzuna configured but ADZUNA_APP_ID / ADZUNA_APP_KEY are not set in .env"
        )
    cfg = cfg or {}
    country = cfg.get("country", "us")
    data = get_json(
        f"https://api.adzuna.com/v1/api/jobs/{country}/search/1",
        params={
            "app_id": app_id,
            "app_key": app_key,
            "what": cfg.get("what", ""),
            "results_per_page": 50,
            "content-type": "application/json",
        },
    )
    return [parse_job(raw) for raw in data.get("results", [])]
