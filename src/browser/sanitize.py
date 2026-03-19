import re

SENSITIVE_PATTERNS = [
    (r"\b\d{3}-\d{2}-\d{4}\b", "[SSN]"),
    (r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b", "[CARD]"),
    (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "[EMAIL]"),
    (r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b", "[PHONE]"),
    (r"sk-[A-Za-z0-9]{48}", "[API_KEY]"),
    (r"xox[baprs]-[A-Za-z0-9]{10,}", "[TOKEN]"),
]


def sanitize_snapshot(text: str) *********REMOVED********* str:
    """Remove sensitive data patterns from page snapshots."""
    for pattern, replacement in SENSITIVE_PATTERNS:
        text = re.sub(pattern, replacement, text)
    return text
