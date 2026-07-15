"""Provider selection and Ollama wire-format tests — no network, no API key."""

import json

import pytest

import autohawk.llm as llm
from autohawk.scoring.llm import ScoreResult


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


# --- selection ---------------------------------------------------------------


def test_auto_returns_none_without_key_or_ollama(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("AUTOHAWK_PROVIDER", "auto")
    monkeypatch.setattr(llm, "ollama_reachable", lambda: False)
    assert llm.get_provider() is None


def test_auto_prefers_anthropic_when_key_present(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-real")
    monkeypatch.setenv("AUTOHAWK_PROVIDER", "auto")
    provider = llm.get_provider()
    assert isinstance(provider, llm.AnthropicProvider)


def test_auto_falls_back_to_ollama(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("AUTOHAWK_PROVIDER", "auto")
    monkeypatch.setattr(llm, "ollama_reachable", lambda: True)
    provider = llm.get_provider()
    assert isinstance(provider, llm.OllamaProvider)


def test_forced_ollama_errors_when_unreachable(monkeypatch):
    monkeypatch.setenv("AUTOHAWK_PROVIDER", "ollama")
    monkeypatch.setattr(llm, "ollama_reachable", lambda: False)
    with pytest.raises(RuntimeError, match="not reachable"):
        llm.get_provider()


def test_none_disables_llm(monkeypatch):
    monkeypatch.setenv("AUTOHAWK_PROVIDER", "none")
    assert llm.get_provider() is None


def test_unknown_provider_errors(monkeypatch):
    monkeypatch.setenv("AUTOHAWK_PROVIDER", "chatgpt")
    with pytest.raises(RuntimeError, match="Unknown AUTOHAWK_PROVIDER"):
        llm.get_provider()


# --- Ollama wire format --------------------------------------------------------


def test_ollama_structured_parses_schema(monkeypatch):
    body = {
        "score": 85,
        "recommendation": "apply",
        "matched_skills": ["Python", "Docker"],
        "gaps": ["5+ years required"],
        "reasoning": "Strong overlap.",
    }
    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["payload"] = kwargs["json"]
        return FakeResponse({"message": {"content": json.dumps(body)}})

    monkeypatch.setattr(llm.requests, "post", fake_post)
    provider = llm.OllamaProvider(model="testmodel", host="http://localhost:11434")
    result = provider.structured("sys prompt", "user prompt", ScoreResult)

    assert result.score == 85
    assert result.recommendation == "apply"
    assert captured["url"].endswith("/api/chat")
    assert captured["payload"]["model"] == "testmodel"
    assert captured["payload"]["format"]["properties"]["score"]  # schema attached
    assert captured["payload"]["stream"] is False


def test_ollama_missing_model_gives_pull_hint(monkeypatch):
    monkeypatch.setattr(
        llm.requests, "post", lambda url, **kw: FakeResponse({}, status_code=404)
    )
    provider = llm.OllamaProvider(model="llama3.1:8b")
    with pytest.raises(RuntimeError, match="ollama pull llama3.1:8b"):
        provider.text("sys", "user")


def test_ollama_empty_response_raises(monkeypatch):
    monkeypatch.setattr(
        llm.requests, "post",
        lambda url, **kw: FakeResponse({"message": {"content": ""}}),
    )
    provider = llm.OllamaProvider(model="testmodel")
    with pytest.raises(RuntimeError, match="empty response"):
        provider.text("sys", "user")
