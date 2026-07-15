from __future__ import annotations

import hashlib
from dataclasses import dataclass, field


@dataclass
class Job:
    source: str
    company: str
    title: str
    url: str
    location: str = ""
    description: str = ""
    posted_at: str = ""  # ISO date string when the source provides one
    tags: list[str] = field(default_factory=list)

    @property
    def id(self) -> str:
        return hashlib.sha1(self.url.encode("utf-8")).hexdigest()[:12]
