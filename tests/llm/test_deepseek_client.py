"""Tests for the v17 DeepSeek client.

The tests are offline: they mock the OpenAI SDK so we never make a
real network call, and they cover the three pieces the rest of the
codebase relies on:

- configuration (placeholder vs real key)
- ``complete`` for plain prompts
- ``extract_risks`` for the structured prompt
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from src.config import Settings, get_settings
from src.llm import (
    DeepSeekClient,
    DeepSeekNotConfigured,
    build_client_from_settings,
)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def test_client_uses_default_base_url_when_env_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DEEPSEEK_BASE_URL", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    client = DeepSeekClient(api_key="sk-real-key")
    assert client.base_url == "https://api.deepseek.com"
    assert client.model == "deepseek-chat"
    assert client.configured is True


def test_client_reads_env_vars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-reasoner")
    client = DeepSeekClient()
    assert client.base_url == "https://example.com/v1"
    assert client.model == "deepseek-reasoner"
    assert client.configured is True


def test_client_treats_placeholder_key_as_unconfigured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for placeholder in (
        "REPLACE_ME",
        "replace-me-with-your-deepseek-api-key",
        "",
        "EMPTY",
        "dummy",
    ):
        monkeypatch.setenv("DEEPSEEK_API_KEY", placeholder)
        client = DeepSeekClient()
        assert client.configured is False, f"placeholder {placeholder!r} should be unconfigured"


def test_complete_raises_when_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "REPLACE_ME")
    client = DeepSeekClient()
    with pytest.raises(DeepSeekNotConfigured):
        client.complete("hello")


def test_extract_risks_raises_when_section_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-real")
    client = DeepSeekClient()
    with pytest.raises(ValueError):
        client.extract_risks("", company_name="Apple")


# ---------------------------------------------------------------------------
# complete()
# ---------------------------------------------------------------------------


def test_complete_calls_openai_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-real")
    fake_response = MagicMock()
    fake_response.choices = [MagicMock(message=MagicMock(content="pong"))]
    with patch("src.llm.deepseek_client.OpenAI") as OpenAIMock:
        sdk = OpenAIMock.return_value
        sdk.chat.completions.create.return_value = fake_response
        client = DeepSeekClient()
        text = client.complete("ping")
    assert text == "pong"
    sdk.chat.completions.create.assert_called_once()
    kwargs = sdk.chat.completions.create.call_args.kwargs
    assert kwargs["model"] == "deepseek-chat"
    assert kwargs["messages"] == [{"role": "user", "content": "ping"}]


def test_complete_prepends_system_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-real")
    fake_response = MagicMock()
    fake_response.choices = [MagicMock(message=MagicMock(content="ok"))]
    with patch("src.llm.deepseek_client.OpenAI") as OpenAIMock:
        sdk = OpenAIMock.return_value
        sdk.chat.completions.create.return_value = fake_response
        client = DeepSeekClient()
        client.complete("ping", system="be terse")
    kwargs = sdk.chat.completions.create.call_args.kwargs
    assert kwargs["messages"][0] == {"role": "system", "content": "be terse"}
    assert kwargs["messages"][1] == {"role": "user", "content": "ping"}


# ---------------------------------------------------------------------------
# extract_risks()
# ---------------------------------------------------------------------------


def test_extract_risks_parses_markdown_code_block(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-real")
    payload = json.dumps(
        {
            "risks": [
                {
                    "risk_factor": "Tariff exposure",
                    "severity": 4,
                    "quote": "tariffs can have a material adverse impact",
                }
            ]
        }
    )
    fake_response = MagicMock()
    fake_response.choices = [
        MagicMock(message=MagicMock(content=f"```json\n{payload}\n```"))
    ]
    with patch("src.llm.deepseek_client.OpenAI") as OpenAIMock:
        sdk = OpenAIMock.return_value
        sdk.chat.completions.create.return_value = fake_response
        client = DeepSeekClient()
        result = client.extract_risks(
            "Item 1A text", company_name="Apple", year=2024
        )
    assert result["company"] == "Apple"
    assert result["year"] == 2024
    assert result["risks"][0]["risk_factor"] == "Tariff exposure"
    assert result["avg_severity"] == 4


def test_extract_risks_parses_string_risks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-real")
    payload = json.dumps({"risks": ["Currency risk", "Cyber risk"]})
    fake_response = MagicMock()
    fake_response.choices = [
        MagicMock(message=MagicMock(content=payload))
    ]
    with patch("src.llm.deepseek_client.OpenAI") as OpenAIMock:
        sdk = OpenAIMock.return_value
        sdk.chat.completions.create.return_value = fake_response
        client = DeepSeekClient()
        result = client.extract_risks("text", "Apple", 2024)
    assert result["risks"] == [
        {"risk_factor": "Currency risk", "severity": 3, "quote": ""},
        {"risk_factor": "Cyber risk", "severity": 3, "quote": ""},
    ]


def test_extract_risks_handles_unparseable_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-real")
    fake_response = MagicMock()
    fake_response.choices = [
        MagicMock(message=MagicMock(content="not json at all"))
    ]
    with patch("src.llm.deepseek_client.OpenAI") as OpenAIMock:
        sdk = OpenAIMock.return_value
        sdk.chat.completions.create.return_value = fake_response
        client = DeepSeekClient()
        result = client.extract_risks("text", "Apple", 2024)
    assert result["risks"] == []
    assert result["avg_severity"] == 0
    assert "raw_response" in result


# ---------------------------------------------------------------------------
# Settings wiring
# ---------------------------------------------------------------------------


def test_settings_exposes_deepseek_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-reasoner")
    settings = Settings()
    assert settings.deepseek_base_url == "https://api.deepseek.com"
    assert settings.deepseek_model == "deepseek-reasoner"
    assert settings.deepseek_api_key == "sk-test"
    assert settings.deepseek_configured() is True


def test_settings_treats_placeholder_as_unconfigured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "REPLACE_ME")
    settings = Settings()
    assert settings.deepseek_configured() is False


def test_build_client_from_settings_uses_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-reasoner")
    client = build_client_from_settings()
    assert client.configured is True
    assert client.model == "deepseek-reasoner"
    get_settings.cache_clear()
