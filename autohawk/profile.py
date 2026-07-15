from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class Profile:
    """The user's master profile loaded from profile.yaml."""

    def __init__(self, data: dict[str, Any]):
        self.data = data

    @classmethod
    def load(cls, path: str | Path = "profile.yaml") -> "Profile":
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(
                f"{path} not found. Run `autohawk init` to create one from the template."
            )
        with path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return cls(data)

    # --- convenience accessors -------------------------------------------------

    @property
    def name(self) -> str:
        return self.data.get("personal", {}).get("name", "")

    @property
    def skills(self) -> list[str]:
        return self.data.get("skills", []) or []

    @property
    def title_keywords(self) -> list[str]:
        return (self.data.get("search", {}) or {}).get("title_keywords", []) or []

    @property
    def sources(self) -> dict[str, Any]:
        return self.data.get("sources", {}) or {}

    # --- prompt rendering ------------------------------------------------------

    def to_prompt_text(self) -> str:
        """Render the profile as stable plain text for the LLM system prompt.

        Kept deterministic (no timestamps, insertion-ordered YAML) so the
        rendered text is byte-identical across calls and cacheable.
        """
        p = self.data.get("personal", {})
        prefs = self.data.get("preferences", {})
        lines = [
            f"Name: {p.get('name', 'N/A')}",
            f"Location: {p.get('location', 'N/A')}",
            f"Summary: {self.data.get('summary', 'N/A')}".strip(),
            f"Skills: {', '.join(self.skills) or 'N/A'}",
        ]
        for exp in self.data.get("experience", []) or []:
            highlights = "; ".join(exp.get("highlights", []) or [])
            lines.append(
                f"Experience: {exp.get('title', '')} at {exp.get('company', '')} "
                f"({exp.get('years', '?')} yrs). {highlights}"
            )
        lines += [
            f"Target roles: {', '.join(prefs.get('roles', []) or []) or 'N/A'}",
            f"Seniority: {prefs.get('seniority', 'N/A')}",
            f"Preferred locations: {', '.join(prefs.get('locations', []) or []) or 'N/A'}",
            f"Needs visa sponsorship: {prefs.get('visa_sponsorship_needed', False)}",
            f"Notice period: {prefs.get('notice_period', 'N/A')}",
        ]
        return "\n".join(lines)
