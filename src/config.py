"""Application settings sourced from environment variables.

Uses ``os.environ`` directly to avoid pulling in ``pydantic-settings`` as a
new dependency. A module-level ``lru_cache`` ensures a single
``Settings`` instance per process.
"""

from __future__ import annotations

import functools
import os
from dataclasses import dataclass, field
from pathlib import Path


def _env(name: str, default: str) -> str:
    """Return the value of ``name`` from ``os.environ`` or ``default``."""
    value = os.environ.get(name)
    return value if value is not None else default


def _env_float(name: str, default: float) -> float:
    """Return an environment variable as float, falling back to ``default``."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    return float(raw)


def _env_path(name: str, default: Path) -> Path:
    """Return an environment variable as ``Path``, falling back to ``default``."""
    raw = os.environ.get(name)
    return Path(raw) if raw else default


@dataclass(frozen=True)
class Settings:
    """Runtime configuration for FinText-LLM components."""

    sec_user_agent: str = field(
        default_factory=lambda: _env(
            "SEC_USER_AGENT", "FinText-LLM contact@example.com"
        )
    )
    sec_rate_limit_per_second: float = field(
        default_factory=lambda: _env_float("SEC_RATE_LIMIT_PER_SECOND", 8.0)
    )
    openai_base_url: str = field(
        default_factory=lambda: _env("OPENAI_BASE_URL", "http://localhost:30000/v1")
    )
    openai_api_key: str = field(default_factory=lambda: _env("OPENAI_API_KEY", "EMPTY"))
    openai_model: str = field(
        default_factory=lambda: _env("OPENAI_MODEL", "gpt-4o-mini")
    )
    llm_model: str = field(
        default_factory=lambda: _env("LLM_MODEL", "Qwen/Qwen3.5-35B-A3B")
    )
    # ---- DeepSeek (https://api-docs.deepseek.com) -------------------------
    deepseek_base_url: str = field(
        default_factory=lambda: _env("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    )
    deepseek_model: str = field(
        default_factory=lambda: _env("DEEPSEEK_MODEL", "deepseek-chat")
    )
    deepseek_api_key: str | None = field(
        default_factory=lambda: os.environ.get("DEEPSEEK_API_KEY")
    )
    deepseek_temperature: float = field(
        default_factory=lambda: _env_float("DEEPSEEK_TEMPERATURE", 0.1)
    )
    deepseek_max_tokens: int = field(
        default_factory=lambda: int(_env("DEEPSEEK_MAX_TOKENS", "2000"))
    )
    deepseek_timeout_s: float = field(
        default_factory=lambda: _env_float("DEEPSEEK_TIMEOUT_S", 60.0)
    )
    llm_provider: str = field(
        default_factory=lambda: _env("LLM_PROVIDER", "sglang")
    )
    hf_edgar_dataset: str = field(
        default_factory=lambda: _env("HF_EDGAR_DATASET", "eloukas/edgar-corpus")
    )
    neo4j_uri: str = field(
        default_factory=lambda: _env("NEO4J_URI", "bolt://localhost:7687")
    )
    neo4j_user: str = field(default_factory=lambda: _env("NEO4J_USER", "neo4j"))
    neo4j_password: str | None = field(
        default_factory=lambda: os.environ.get("NEO4J_PASSWORD")
    )
    cache_dir: Path = field(
        default_factory=lambda: _env_path("CACHE_DIR", Path(".cache/fintext_llm"))
    )
    search_provider_order: str = field(
        default_factory=lambda: _env(
            "SEARCH_PROVIDER_ORDER", "duckduckgo"
        )
    )

    def deepseek_configured(self) -> bool:
        """Return ``True`` when a real DeepSeek API key is present.

        Placeholder strings (e.g. ``REPLACE_ME``, ``replace-me-...``,
        empty / ``EMPTY`` / ``dummy``) are treated as "not configured"
        so demo environments never accidentally send requests to the
        real API.
        """
        key = self.deepseek_api_key
        if not key:
            return False
        lowered = key.strip().lower()
        if not lowered or lowered in {"empty", "dummy", "replace_me"}:
            return False
        if lowered.startswith("replace-me"):
            return False
        return True


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide cached ``Settings`` instance."""
    return Settings()
