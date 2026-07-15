"""Zero-cost fallback scorer: skill-keyword overlap between profile and posting."""

from __future__ import annotations

import re


def keyword_score(
    skills: list[str], title: str, description: str
) -> tuple[int, list[str]]:
    """Return (score 0-100, matched skills).

    Title matches weigh double — a skill in the job title is a much stronger
    signal than one buried in the description boilerplate.
    """
    if not skills:
        return 0, []
    text_title = title.lower()
    text_desc = description.lower()
    matched: list[str] = []
    points = 0.0
    for skill in skills:
        pattern = re.escape(skill.lower())
        in_title = re.search(pattern, text_title) is not None
        in_desc = re.search(pattern, text_desc) is not None
        if in_title or in_desc:
            matched.append(skill)
            points += 2.0 if in_title else 1.0
    # Normalize: matching ~half your skills in descriptions ≈ 100
    max_points = max(len(skills) / 2.0, 1.0)
    score = min(int(round(points / max_points * 100)), 100)
    return score, matched
