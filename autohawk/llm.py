"""Pluggable LLM providers.

Two backends behind one interface:

- AnthropicProvider — hosted Claude, best quality, needs ANTHROPIC_API_KEY.
- OllamaProvider   — local models via Ollama (https://ollama.com), zero cost,
                     no account. Structured output enforced with Ollama's
                     `format` parameter (JSON schema).

Selection (env var AUTOHAWK_PROVIDER):
  auto      -> Anthropic if ANTHROPIC_API_KEY is set, else Ollama if it is
               running, else None (callers fall back to keyword scoring)
  anthropic -> force Anthropic (error if no key)
  ollama    -> force Ollama (error if not reachable)
  none      -> disable LLM features
"""

from __future__ import annotations

import os
from typing import Protocol, TypeVar

import requests
from pydantic import BaseModel

DEFAULT_ANTHROPIC_MODEL = "claude-opus-4-8"
DEFAULT_OLLAMA_MODEL = "llama3.1:8b"
DEFAULT_OLLAMA_HOST = "http://localhost:11434"
# CPU-only inference on a small server can take minutes per job
OLLAMA_TIMEOUT = 600

T = TypeVar("T", bound=BaseModel)


class Provider(Protocol):
    def describe(self) -> str: ...
    def structured(self, system: str, user: str, schema: type[T]) -> T: ...
    def text(self, system: str, user: str) -> str: ...


# --- Anthropic ------------------------------------------------------------


class AnthropicProvider:
    def __init__(self, model: str | None = None):
        import anthropic  # imported lazily so Ollama-only installs never touch it

        self._anthropic = anthropic
        self.client = anthropic.Anthropic()
        self.model = model or os.environ.get("AUTOHAWK_MODEL") or DEFAULT_ANTHROPIC_MODEL

    def describe(self) -> str:
        return f"anthropic ({self.model})"

    def _system_blocks(self, system: str) -> list[dict]:
        # The system prompt is stable across a scoring run — cache it so
        # scoring N jobs reuses the prefix instead of re-paying for it.
        return [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]

    def structured(self, system: str, user: str, schema: type[T]) -> T:
        response = self.client.messages.parse(
            model=self.model,
            max_tokens=2048,
            output_config={"effort": "low"},  # scoring is a simple, high-volume task
            system=self._system_blocks(system),
            messages=[{"role": "user", "content": user}],
            output_format=schema,
        )
        result = response.parsed_output
        if result is None:
            raise RuntimeError("model returned no parseable output")
        return result

    def text(self, system: str, user: str) -> str:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            thinking={"type": "adaptive"},
            system=self._system_blocks(system),
            messages=[{"role": "user", "content": user}],
        )
        if response.stop_reason == "refusal":
            raise RuntimeError("model declined this request")
        return next(b.text for b in response.content if b.type == "text")


# --- Ollama ---------------------------------------------------------------


def ollama_host() -> str:
    return (os.environ.get("OLLAMA_HOST") or DEFAULT_OLLAMA_HOST).rstrip("/")


def ollama_reachable(host: str | None = None) -> bool:
    try:
        return requests.get(f"{host or ollama_host()}/api/tags", timeout=3).ok
    except requests.RequestException:
        return False


class OllamaProvider:
    def __init__(self, model: str | None = None, host: str | None = None):
        self.host = (host or ollama_host()).rstrip("/")
        self.model = model or os.environ.get("AUTOHAWK_OLLAMA_MODEL") or DEFAULT_OLLAMA_MODEL

    def describe(self) -> str:
        return f"ollama ({self.model} @ {self.host})"

    def _chat(self, system: str, user: str, fmt: dict | None = None) -> str:
        payload: dict = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            # Default Ollama context (2048) truncates long job descriptions;
            # low temperature keeps scores consistent between runs.
            "options": {"temperature": 0.2, "num_ctx": 8192},
        }
        if fmt is not None:
            payload["format"] = fmt
        resp = requests.post(f"{self.host}/api/chat", json=payload, timeout=OLLAMA_TIMEOUT)
        if resp.status_code == 404:
            raise RuntimeError(
                f"Ollama has no model '{self.model}'. Pull it first:  ollama pull {self.model}"
            )
        resp.raise_for_status()
        content = resp.json().get("message", {}).get("content", "")
        if not content:
            raise RuntimeError("Ollama returned an empty response")
        return content

    def structured(self, system: str, user: str, schema: type[T]) -> T:
        # Ollama constrains generation to the schema when `format` is set
        content = self._chat(system, user, fmt=schema.model_json_schema())
        return schema.model_validate_json(content)

    def text(self, system: str, user: str) -> str:
        return self._chat(system, user)


# --- selection --------------------------------------------------------------


def get_provider() -> Provider | None:
    """Resolve the configured provider, or None when keyword fallback applies."""
    choice = (os.environ.get("AUTOHAWK_PROVIDER") or "auto").strip().lower()
    if choice == "anthropic":
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError("AUTOHAWK_PROVIDER=anthropic but ANTHROPIC_API_KEY is not set")
        return AnthropicProvider()
    if choice == "ollama":
        if not ollama_reachable():
            raise RuntimeError(
                f"AUTOHAWK_PROVIDER=ollama but Ollama is not reachable at {ollama_host()}. "
                "Install it from https://ollama.com and make sure it is running "
                "(`ollama serve`, or the desktop app)."
            )
        return OllamaProvider()
    if choice in ("none", "keyword"):
        return None
    if choice == "auto":
        if os.environ.get("ANTHROPIC_API_KEY"):
            return AnthropicProvider()
        if ollama_reachable():
            return OllamaProvider()
        return None
    raise RuntimeError(
        f"Unknown AUTOHAWK_PROVIDER '{choice}' (use auto, anthropic, ollama, or none)"
    )
