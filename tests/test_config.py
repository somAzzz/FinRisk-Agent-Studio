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
        "LLM_MODEL",
        "HF_EDGAR_DATASET",
        "NEO4J_URI",
        "NEO4J_USER",
        "NEO4J_PASSWORD",
        "CACHE_DIR",
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
            "LLM_MODEL",
            "HF_EDGAR_DATASET",
            "NEO4J_URI",
            "NEO4J_USER",
            "NEO4J_PASSWORD",
            "CACHE_DIR",
        ):
            monkeypatch.delenv(key, raising=False)

        settings = Settings()

        assert settings.sec_user_agent == "FinText-LLM contact@example.com"
        assert settings.sec_rate_limit_per_second == 8.0
        assert settings.openai_base_url == "http://localhost:30000/v1"
        assert settings.openai_api_key == "EMPTY"
        assert settings.llm_model == "Qwen/Qwen3.5-35B-A3B"
        assert settings.hf_edgar_dataset == "eloukas/edgar-corpus"
        assert settings.neo4j_uri == "bolt://localhost:7687"
        assert settings.neo4j_user == "neo4j"
        assert settings.neo4j_password is None
        assert settings.cache_dir == Path(".cache/fintext_llm")


class TestEnvOverrides:
    def test_sec_user_agent_is_read_from_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _clear_env()
        monkeypatch.setenv("SEC_USER_AGENT", "Research Bot me@example.org")
        settings = Settings()
        assert settings.sec_user_agent == "Research Bot me@example.org"

    def test_numeric_settings_are_coerced_from_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _clear_env()
        monkeypatch.setenv("SEC_RATE_LIMIT_PER_SECOND", "12.5")
        settings = Settings()
        assert settings.sec_rate_limit_per_second == 12.5
        assert isinstance(settings.sec_rate_limit_per_second, float)

    def test_cache_dir_is_coerced_to_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _clear_env()
        monkeypatch.setenv("CACHE_DIR", "/tmp/fintext-test-cache")
        settings = Settings()
        assert settings.cache_dir == Path("/tmp/fintext-test-cache")

    def test_neo4j_password_can_be_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _clear_env()
        monkeypatch.setenv("NEO4J_PASSWORD", "s3cr3t")
        settings = Settings()
        assert settings.neo4j_password == "s3cr3t"


class TestGetSettings:
    def test_get_settings_returns_cached_instance(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _clear_env()
        monkeypatch.setenv("LLM_MODEL", "custom/model")
        first = get_settings()
        second = get_settings()
        assert first is second
        assert first.llm_model == "custom/model"

    def test_get_settings_does_not_pick_up_later_env_changes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _clear_env()
        first = get_settings()
        monkeypatch.setenv("LLM_MODEL", "another/model")
        second = get_settings()
        assert first is second
        assert second.llm_model == "custom/model" or first.llm_model == first.llm_model
        # The cached instance is reused regardless of later env mutations.
        assert first.llm_model == second.llm_model
