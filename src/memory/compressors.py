"""Deterministic compressors for ContextPack evidence snippets."""

from __future__ import annotations


def clamp_text(value: str | None, max_chars: int) -> str | None:
    """Return ``value`` truncated to ``max_chars`` without LLM summarization."""
    if value is None:
        return None
    stripped = " ".join(value.split())
    if len(stripped) <= max_chars:
        return stripped
    return stripped[: max(0, max_chars - 3)].rstrip() + "..."


def estimate_tokens(text: str, chars_per_token: int = 4) -> int:
    """Estimate token count using a simple character heuristic."""
    return max(1, len(text) // chars_per_token)


__all__ = ["clamp_text", "estimate_tokens"]
