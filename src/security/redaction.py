"""Small text redaction helpers for logs and audit rows.

The workflow stores LLM prompts and responses for observability. That is useful
when debugging extraction quality, but it should not persist obvious secrets or
personal identifiers. Keep this helper conservative and deterministic: it only
redacts high-confidence patterns and leaves ordinary financial text intact.
"""

from __future__ import annotations

import re
from typing import Any

SENSITIVE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[SSN]"),
    (re.compile(r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b"), "[CARD]"),
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "[EMAIL]"),
    (re.compile(r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b"), "[PHONE]"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"), "[API_KEY]"),
    (re.compile(r"\b(?:xox[baprs]-)[A-Za-z0-9-]{10,}\b"), "[TOKEN]"),
    (re.compile(r"\b(?:Bearer|Token)\s+[A-Za-z0-9._~+/=-]{20,}\b", re.IGNORECASE), "[TOKEN]"),
)


def redact_text(text: str) -> str:
    """Return ``text`` with high-confidence sensitive values replaced."""
    out = text
    for pattern, replacement in SENSITIVE_PATTERNS:
        out = pattern.sub(replacement, out)
    return out


def redact_obj(value: Any) -> Any:
    """Recursively redact strings inside JSON-like values."""
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        return [redact_obj(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_obj(item) for item in value)
    if isinstance(value, dict):
        return {key: redact_obj(item) for key, item in value.items()}
    return value


__all__ = ["SENSITIVE_PATTERNS", "redact_obj", "redact_text"]
