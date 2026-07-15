"""Claude-based job-fit scoring with structured outputs.

Uses `client.messages.parse()` so the response is validated against the
ScoreResult schema automatically. The system prompt (instructions + profile)
is stable across every call in a run and carries a cache_control breakpoint,
so repeated scoring calls reuse the cached prefix.
"""

from __future__ import annotations

import os
from typing import Literal

import anthropic
from pydantic import BaseModel, Field

from ..profile import Profile
from ..utils import truncate

DEFAULT_MODEL = "claude-opus-4-8"
DESCRIPTION_CHAR_LIMIT = 8000


class ScoreResult(BaseModel):
    score: int = Field(description="Fit score from 0 (no fit) to 100 (perfect fit)")
    recommendation: Literal["strong_apply", "apply", "maybe", "skip"]
    matched_skills: list[str] = Field(
        description="Candidate skills that this job explicitly needs"
    )
    gaps: list[str] = Field(
        description="Requirements the candidate does not clearly meet"
    )
    reasoning: str = Field(description="Two or three sentences justifying the score")


def llm_available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


class LLMScorer:
    def __init__(self, profile: Profile, model: str | None = None):
        self.client = anthropic.Anthropic()
        self.model = model or os.environ.get("AUTOHAWK_MODEL") or DEFAULT_MODEL
        # Stable system prompt — instructions first, profile after, cache marker
        # on the last block so the whole prefix is reused across scoring calls.
        self.system = [
            {
                "type": "text",
                "text": (
                    "You are a rigorous job-fit evaluator. Score how well the candidate "
                    "below fits a job posting. Be honest: penalize seniority mismatches, "
                    "hard requirements the candidate lacks (clearance, degree, specific "
                    "location, visa constraints), and stacks far from their experience. "
                    "Reward strong overlap in core skills and target roles. "
                    "Calibration: 80+ means apply today; 60-79 solid fit; 40-59 stretch; "
                    "below 40 skip.\n\n"
                    "CANDIDATE PROFILE:\n" + profile.to_prompt_text()
                ),
                "cache_control": {"type": "ephemeral"},
            }
        ]

    def score(self, title: str, company: str, location: str, description: str) -> ScoreResult:
        posting = (
            f"JOB POSTING\nTitle: {title}\nCompany: {company}\n"
            f"Location: {location}\n\n{truncate(description, DESCRIPTION_CHAR_LIMIT)}"
        )
        response = self.client.messages.parse(
            model=self.model,
            max_tokens=2048,
            output_config={"effort": "low"},  # scoring is a simple, high-volume task
            system=self.system,
            messages=[{"role": "user", "content": posting}],
            output_format=ScoreResult,
        )
        result = response.parsed_output
        if result is None:
            raise RuntimeError("model returned no parseable score")
        result.score = max(0, min(result.score, 100))
        return result
