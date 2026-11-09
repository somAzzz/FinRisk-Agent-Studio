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
from typing import Literal

AgentRuntimeMode = Literal["pydantic_ai"]
StoredAgentRuntimeMode = Literal[
    "legacy",
    "pydantic_ai_shadow",
    "pydantic_ai_primary",
    "pydantic_ai",
]


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


def _env_optional(name: str) -> str | None:
    """Return a stripped environment value, treating blank as missing."""
    raw = os.environ.get(name)
    if raw is None:
        return None
    return raw.strip() or None


def _env_optional_float(
    name: str,
    default: float | None = None,
) -> float | None:
    """Parse an optional float environment variable."""
    raw = _env_optional(name)
    return default if raw is None else float(raw)


def _env_optional_int(
    name: str,
    default: int | None = None,
) -> int | None:
    """Parse an optional integer environment variable."""
    raw = _env_optional(name)
    return default if raw is None else int(raw)


def _env_path(name: str, default: Path) -> Path:
    """Return an environment variable as ``Path``, falling back to ``default``."""
    raw = os.environ.get(name)
    return Path(raw) if raw else default


_PLACEHOLDER_TOKENS = frozenset({"empty", "dummy", "replace_me", "replace-me", "changeme", "todo"})


def credential_configured(value: str | None) -> bool:
    """Return whether a cloud credential is non-empty and non-placeholder."""
    if not value:
        return False

    normalized = value.strip().lower()
    if not normalized or normalized in _PLACEHOLDER_TOKENS:
        return False

    return not normalized.startswith(("replace-me", "replace_me"))


@dataclass(frozen=True)
class Settings:
    """Runtime configuration for FinRisk-Agent-Studio components."""

    # Pydantic AI is the sole production runtime. AGENT_RUNTIME_MODE is no
    # longer read, so stale deployment variables cannot reactivate old code.
    agent_runtime_mode: AgentRuntimeMode = "pydantic_ai"

    sec_user_agent: str = field(
        default_factory=lambda: _env("SEC_USER_AGENT", "FinRisk-Agent-Studio contact@example.com")
    )
    sec_rate_limit_per_second: float = field(default_factory=lambda: _env_float("SEC_RATE_LIMIT_PER_SECOND", 8.0))

    # ---- LLM deployment and generation policy ---------------------------
    llm_provider: str = field(default_factory=lambda: _env("LLM_PROVIDER", "sglang"))
    llm_temperature: float | None = field(default_factory=lambda: _env_optional_float("LLM_TEMPERATURE"))
    llm_max_tokens: int | None = field(default_factory=lambda: _env_optional_int("LLM_MAX_TOKENS"))
    llm_timeout_seconds: float | None = field(default_factory=lambda: _env_optional_float("LLM_TIMEOUT_SECONDS", 60.0))
    llm_thinking: str | None = field(default_factory=lambda: _env_optional("LLM_THINKING"))

    sglang_base_url: str = field(default_factory=lambda: _env("SGLANG_BASE_URL", "http://localhost:30000/v1"))
    sglang_model: str = field(default_factory=lambda: _env("SGLANG_MODEL", "qwen3.8-27b"))
    sglang_api_key: str = field(default_factory=lambda: _env("SGLANG_API_KEY", "EMPTY"))
    vllm_base_url: str = field(default_factory=lambda: _env("VLLM_BASE_URL", "http://localhost:8000/v1"))
    vllm_model: str = field(default_factory=lambda: _env("VLLM_MODEL", "Qwen/Qwen3.5-35B-A3B"))
    vllm_api_key: str = field(default_factory=lambda: _env("VLLM_API_KEY", "dummy"))
    # ---- DeepSeek (https://api-docs.deepseek.com) -------------------------
    deepseek_model: str = field(default_factory=lambda: _env("DEEPSEEK_MODEL", "deepseek-v4-flash"))
    deepseek_api_key: str | None = field(default_factory=lambda: _env_optional("DEEPSEEK_API_KEY"))
    openai_base_url: str = field(default_factory=lambda: _env("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    openai_model: str = field(default_factory=lambda: _env("OPENAI_MODEL", "gpt-4o-mini"))
    openai_api_key: str | None = field(default_factory=lambda: _env_optional("OPENAI_API_KEY"))

    hf_edgar_dataset: str = field(default_factory=lambda: _env("HF_EDGAR_DATASET", "eloukas/edgar-corpus"))
    neo4j_uri: str = field(default_factory=lambda: _env("NEO4J_URI", "bolt://localhost:7687"))
    neo4j_user: str = field(default_factory=lambda: _env("NEO4J_USER", "neo4j"))
    neo4j_password: str | None = field(default_factory=lambda: os.environ.get("NEO4J_PASSWORD"))
    cache_dir: Path = field(default_factory=lambda: _env_path("CACHE_DIR", Path(".cache/finrisk_agent_studio")))
    search_provider_order: str = field(default_factory=lambda: _env("SEARCH_PROVIDER_ORDER", "duckduckgo"))
    # ---- API auth (R1) ----------------------------------------------------
    # Comma-separated allowlist of accepted ``X-API-Key`` values. Empty
    # means "auth not configured" — the API fails closed (401) unless
    # ``AUTH_DISABLED=1`` is set explicitly. Reuse the
    # ``deepseek_configured()`` placeholder-rejection policy.
    api_keys: tuple[str, ...] = field(default_factory=lambda: _parse_api_keys(os.environ.get("FINRISK_API_KEYS")))

    def deepseek_configured(self) -> bool:
        """Return ``True`` when a real DeepSeek API key is present.

        Placeholder strings (e.g. ``REPLACE_ME``, ``replace-me-...``,
        empty / ``EMPTY`` / ``dummy``) are treated as "not configured"
        so demo environments never accidentally send requests to the
        real API.
        """
        return credential_configured(self.deepseek_api_key)

    def openai_configured(self) -> bool:
        """Return ``True`` when a real OpenAI API key is present."""
        return credential_configured(self.openai_api_key)

    def api_keys_configured(self) -> bool:
        """Return ``True`` when at least one non-placeholder API key is set."""
        return len(self.api_keys) > 0


def _parse_api_keys(raw: str | None) -> tuple[str, ...]:
    """Parse a comma-separated allowlist, dropping blanks and placeholders."""
    if not raw:
        return ()
    return tuple(token for piece in raw.split(",") if (token := piece.strip()) and credential_configured(token))


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide cached ``Settings`` instance."""
    return Settings()
