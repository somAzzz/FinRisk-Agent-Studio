from src.security.redaction import SENSITIVE_PATTERNS, redact_text


def sanitize_snapshot(text: str) -> str:
    """Remove sensitive data patterns from page snapshots."""
    return redact_text(text)


__all__ = ["SENSITIVE_PATTERNS", "sanitize_snapshot"]
