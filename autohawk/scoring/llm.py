"""LLM job-fit scoring — provider-agnostic (Claude or local Ollama).

Structured output is enforced by the provider: Anthropic via
`messages.parse()` with a Pydantic schema, Ollama via its `format`
JSON-schema parameter. Same ScoreResult either way.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ..llm import Provider
from ..profile import Profile
from ..utils import truncate

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


class LLMScorer:
    def __init__(self, profile: Profile, provider: Provider):
        self.provider = provider
        # Stable across the whole run — instructions first, profile after
        self.system = (
            "You are a rigorous job-fit evaluator. Score how well the candidate "
            "below fits a job posting. Be honest: penalize seniority mismatches, "
            "hard requirements the candidate lacks (clearance, degree, specific "
            "location, visa constraints), and stacks far from their experience. "
            "Reward strong overlap in core skills and target roles. "
            "Calibration: 80+ means apply today; 60-79 solid fit; 40-59 stretch; "
            "below 40 skip.\n\n"
            "CANDIDATE PROFILE:\n" + profile.to_prompt_text()
        )

    def score(self, title: str, company: str, location: str, description: str) -> ScoreResult:
        posting = (
            f"JOB POSTING\nTitle: {title}\nCompany: {company}\n"
            f"Location: {location}\n\n{truncate(description, DESCRIPTION_CHAR_LIMIT)}"
        )
        result = self.provider.structured(self.system, posting, ScoreResult)
        result.score = max(0, min(result.score, 100))
        return result
