"""Hacker News "Ask HN: Who is hiring?" monthly thread, via the Algolia HN API.

Top-level comments are job posts, conventionally headed
"Company | Role | Location | Salary | ..." on the first line.
No auth needed. Each comment's permalink is the dedupe URL.
"""

from __future__ import annotations

from ..models import Job
from ..utils import strip_html
from .http import get_json

SEARCH_URL = "https://hn.algolia.com/api/v1/search_by_date"
ITEM_URL = "https://hn.algolia.com/api/v1/items/{id}"


def latest_thread_id() -> str | None:
    """Find the most recent 'Who is hiring?' story posted by the whoishiring bot."""
    data = get_json(
        SEARCH_URL,
        params={"tags": "story,author_whoishiring", "hitsPerPage": 10},
    )
    for hit in data.get("hits", []):
        if "who is hiring" in (hit.get("title") or "").lower():
            return str(hit.get("objectID"))
    return None


def parse_comment(raw: dict) -> Job | None:
    """One top-level comment -> one Job, or None for deleted/unparseable posts."""
    raw_html = raw.get("text") or ""
    text = strip_html(raw_html)
    if not text or raw.get("id") is None:
        return None
    # HN separates the "Company | Role | Location" header from the body with
    # the first <p>, so split on the raw HTML before stripping tags.
    first_line = strip_html(raw_html.partition("<p>")[0]).partition("\n")[0]
    parts = [p.strip() for p in first_line.split("|") if p.strip()]
    if not parts:
        return None
    company = parts[0][:80]
    # Everything after the company keeps role + location + salary, so the
    # title pre-filter still sees the role keywords.
    title = " | ".join(parts[1:])[:140] or first_line[:140]
    return Job(
        source="hn_whoishiring",
        company=company,
        title=title,
        url=f"https://news.ycombinator.com/item?id={raw['id']}",
        description=text,
        posted_at=(raw.get("created_at") or "")[:10],
    )


def fetch(cfg: dict | None) -> list[Job]:
    thread_id = latest_thread_id()
    if thread_id is None:
        return []
    item = get_json(ITEM_URL.format(id=thread_id))
    jobs = []
    for child in item.get("children", []):
        job = parse_comment(child)
        if job is not None:
            jobs.append(job)
    return jobs
