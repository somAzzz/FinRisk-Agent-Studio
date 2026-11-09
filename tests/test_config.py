"""Tests for the Settings configuration system."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from src.config import Settings, get_settings


@pytest.fixture(autouse=True)
def _reset_settings_cache() -> None:
    """Clear the lru_cache around get_settings for every test."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _clear_env() -> None:
    """Strip every variable read by ``Settings`` from ``os.environ``."""
    for key in (
        "SEC_USER_AGENT",
        "SEC_RATE_LIMIT_PER_SECOND",
        "OPENAI_BASE_URL",
        "OPENAI_API_KEY",
        "OPENAI_MODEL",
        "LLM_PROVIDER",
        "LLM_TEMPERATURE",
        "LLM_MAX_TOKENS",
        "LLM_TIMEOUT_SECONDS",
        "LLM_THINKING",
        "AGENT_RUNTIME_MODE",
        "SGLANG_BASE_URL",
        "SGLANG_MODEL",
        "SGLANG_API_KEY",
        "VLLM_BASE_URL",
        "VLLM_MODEL",
        "VLLM_API_KEY",
        "DEEPSEEK_MODEL",
        "DEEPSEEK_API_KEY",
        "DEEPSEEK_TEMPERATURE",
        "DEEPSEEK_MAX_TOKENS",
        "DEEPSEEK_TIMEOUT_S",
        "HF_EDGAR_DATASET",
        "NEO4J_URI",
        "NEO4J_USER",
        "NEO4J_PASSWORD",
        "CACHE_DIR",
        "SEARCH_PROVIDER_ORDER",
        "FINRISK_API_KEYS",
    ):
        os.environ.pop(key, None)


class TestDefaults:
    def test_defaults_match_plan(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _clear_env()
        for key in (
            "SEC_USER_AGENT",
            "SEC_RATE_LIMIT_PER_SECOND",
            "OPENAI_BASE_URL",
            "OPENAI_API_KEY",
            "OPENAI_MODEL",
            "LLM_PROVIDER",
            "LLM_TEMPERATURE",
            "LLM_MAX_TOKENS",
            "LLM_TIMEOUT_SECONDS",
            "LLM_THINKING",
            "AGENT_RUNTIME_MODE",
            "HF_EDGAR_DATASET",
            "NEO4J_URI",
            "NEO4J_USER",
            "NEO4J_PASSWORD",
            "CACHE_DIR",
        ):
            monkeypatch.delenv(key, raising=False)

        settings = Settings()

        assert settings.sec_user_agent == "FinRisk-Agent-Studio contact@example.com"
        assert settings.agent_runtime_mode == "pydantic_ai"
        assert settings.sec_rate_limit_per_second == 8.0
        assert settings.openai_base_url == "https://api.openai.com/v1"
        assert settings.openai_api_key is None
        assert settings.llm_provider == "sglang"
        assert settings.llm_temperature is None
        assert settings.llm_max_tokens is None
        assert settings.llm_timeout_seconds == 60.0
        assert settings.llm_thinking is None
        assert settings.sglang_base_url == "http://localhost:30000/v1"
        assert settings.vllm_base_url == "http://localhost:8000/v1"
        assert settings.hf_edgar_dataset == "eloukas/edgar-corpus"
        assert settings.neo4j_uri == "bolt://localhost:7687"
        assert settings.neo4j_user == "neo4j"
        assert settings.neo4j_password is None
        assert settings.cache_dir == Path(".cache/finrisk_agent_studio")


class TestEnvOverrides:
    def test_sec_user_agent_is_read_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _clear_env()
        monkeypatch.setenv("SEC_USER_AGENT", "Research Bot me@example.org")
        settings = Settings()
        assert settings.sec_user_agent == "Research Bot me@example.org"

    def test_numeric_settings_are_coerced_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _clear_env()
        monkeypatch.setenv("SEC_RATE_LIMIT_PER_SECOND", "12.5")
        monkeypatch.setenv("LLM_TEMPERATURE", "0")
        monkeypatch.setenv("LLM_MAX_TOKENS", "2048")
        monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "45.5")
        settings = Settings()
        assert settings.sec_rate_limit_per_second == 12.5
        assert isinstance(settings.sec_rate_limit_per_second, float)
        assert settings.llm_temperature == 0
        assert settings.llm_max_tokens == 2048
        assert settings.llm_timeout_seconds == 45.5

    def test_cache_dir_is_coerced_to_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _clear_env()
        monkeypatch.setenv("CACHE_DIR", "/tmp/finrisk-test-cache")
        settings = Settings()
        assert settings.cache_dir == Path("/tmp/finrisk-test-cache")

    def test_neo4j_password_can_be_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _clear_env()
        monkeypatch.setenv("NEO4J_PASSWORD", "s3cr3t")
        settings = Settings()
        assert settings.neo4j_password == "s3cr3t"

    @pytest.mark.parametrize("mode", ["legacy", "pydantic_ai_shadow", "experimental"])
    def test_agent_runtime_mode_env_cannot_reactivate_removed_runtime(
        self, monkeypatch: pytest.MonkeyPatch, mode: str
    ) -> None:
        _clear_env()
        monkeypatch.setenv("AGENT_RUNTIME_MODE", mode)

        assert Settings().agent_runtime_mode == "pydantic_ai"


class TestGetSettings:
    def test_get_settings_returns_cached_instance(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _clear_env()
        monkeypatch.setenv("LLM_TEMPERATURE", "0")
        first = get_settings()
        second = get_settings()
        assert first is second
        assert first.llm_temperature == 0

    def test_get_settings_does_not_pick_up_later_env_changes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _clear_env()
        monkeypatch.setenv("LLM_TEMPERATURE", "0.1")
        first = get_settings()
        monkeypatch.setenv("LLM_TEMPERATURE", "0.9")
        second = get_settings()
        assert first is second
        assert first.llm_temperature == 0.1
        assert second.llm_temperature == 0.1
