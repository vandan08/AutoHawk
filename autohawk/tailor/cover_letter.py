"""Tailored cover-letter generation — provider-agnostic (Claude or local Ollama)."""

from __future__ import annotations

from ..llm import Provider
from ..profile import Profile
from ..utils import truncate

_SYSTEM = (
    "You write short, specific, human-sounding cover letters. Rules: maximum 250 "
    "words; open with a concrete hook tied to the company or role, never 'I am "
    "writing to apply'; weave in 2-3 of the candidate's most relevant skills or "
    "projects as evidence, not a list; mirror the language of the posting where "
    "natural; close with one confident sentence. Never invent experience the "
    "candidate does not have. Output only the letter body — no subject line, no "
    "placeholder brackets, no commentary."
)


def generate_cover_letter(
    profile: Profile,
    title: str,
    company: str,
    description: str,
    provider: Provider,
) -> str:
    user = (
        f"CANDIDATE:\n{profile.to_prompt_text()}\n\n"
        f"JOB: {title} at {company}\n\n"
        f"POSTING:\n{truncate(description, 6000)}\n\n"
        "Write the cover letter."
    )
    return provider.text(_SYSTEM, user).strip()
