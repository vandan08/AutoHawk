"""Tailored cover-letter generation with Claude."""

from __future__ import annotations

import os

import anthropic

from ..profile import Profile
from ..utils import truncate

DEFAULT_MODEL = "claude-opus-4-8"

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
    model: str | None = None,
) -> str:
    client = anthropic.Anthropic()
    model = model or os.environ.get("AUTOHAWK_MODEL") or DEFAULT_MODEL
    response = client.messages.create(
        model=model,
        max_tokens=2048,
        thinking={"type": "adaptive"},
        system=_SYSTEM,
        messages=[
            {
                "role": "user",
                "content": (
                    f"CANDIDATE:\n{profile.to_prompt_text()}\n\n"
                    f"JOB: {title} at {company}\n\n"
                    f"POSTING:\n{truncate(description, 6000)}\n\n"
                    "Write the cover letter."
                ),
            }
        ],
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("model declined to generate this letter")
    return next(b.text for b in response.content if b.type == "text").strip()
