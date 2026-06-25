"""v18 evidence helpers for the search-extraction layer.

Real-mode search snippets (Brave, DuckDuckGo, browser fetches)
are converted to v18 ``NormalizedSupplyChainEvidence`` rows via
:func:`build_evidence_from_search`. The function enforces the
v18 spec 03 contract:

- snippets with no ``url`` are not confirmed;
- snippets with no ``quote`` are not confirmed;
- everything else is confirmed.

The function is intentionally pure and side-effect-free so
unit tests can call it directly.
"""

from __future__ import annotations

import hashlib
from typing import Any

from src.workflows.state import utcnow


def _evidence_id(url: str | None, quote: str) -> str:
    """Generate a stable ``sc:web:*`` evidence id."""
    payload = f"{url or 'no-url'}|{quote}".encode()
    digest = hashlib.sha1(payload).hexdigest()[:12]
    return f"sc:web:{digest}"


def build_evidence_from_search(
    snippet: dict[str, Any],
    *,
    query: str,
    confidence: float | None = None,
) -> dict[str, Any]:
    """Convert a search snippet to a v18 evidence dict.

    Returns a plain dict (rather than a Pydantic model) so the
    function is easy to compose with the existing ``SearchRouter``
    which is not v18-aware. The dict matches the
    :class:`NormalizedSupplyChainEvidence` schema.
    """
    url = (snippet.get("url") or "").strip()
    title = (snippet.get("title") or "").strip()
    quote = (snippet.get("snippet") or snippet.get("quote") or "").strip()
    is_confirmed = bool(url) and bool(quote)
    score = (
        confidence
        if confidence is not None
        else (0.7 if is_confirmed else 0.3)
    )
    return {
        "evidence_id": _evidence_id(url or None, quote),
        "source_type": "web",
        "source_name": _domain_from_url(url) if url else None,
        "url": url or None,
        "title": title or None,
        "quote": quote,
        "summary": quote or title,
        "retrieved_at": utcnow(),
        "published_at": None,
        "confidence": float(score),
        "is_confirmed": is_confirmed,
        "metadata": {"query": query},
    }


def _domain_from_url(url: str) -> str:
    from urllib.parse import urlparse

    try:
        return urlparse(url).netloc or url
    except ValueError:
        return url


__all__ = ["build_evidence_from_search"]
