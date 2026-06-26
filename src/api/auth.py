"""API authentication for FinRisk Agent Studio.

The public API uses a simple ``X-API-Key`` header. The allowlist is
configured via the ``FINRISK_API_KEYS`` environment variable as a
comma-separated list. Comparison uses :func:`secrets.compare_digest`
to avoid timing oracles.

Escape hatches (intentional, used by tests and local development):

- ``AUTH_DISABLED=1`` — bypass the dependency entirely. The
  :class:`fastapi.FastAPI` is still constructed normally; handlers
  just no longer require the header. This mirrors the existing
  ``FINRISK_SKIP_BACKGROUND=1`` pattern.
- ``api_keys`` empty / unset — auth is treated as "not configured";
  we fail closed (401) so a misconfigured deployment never serves
  unauthenticated traffic by accident.
"""

from __future__ import annotations

import os
import secrets
from collections.abc import Iterable

from fastapi import Header, HTTPException, status

_PLACEHOLDER_TOKENS = frozenset(
    {"empty", "dummy", "replace_me", "replace-me", "changeme", "todo"}
)


def _parse_keys(raw: str | None) -> tuple[str, ...]:
    """Parse a comma-separated allowlist, stripping blanks and placeholders."""
    if not raw:
        return ()
    out: list[str] = []
    for piece in raw.split(","):
        token = piece.strip()
        if not token:
            continue
        if token.lower() in _PLACEHOLDER_TOKENS or token.lower().startswith(
            "replace-me"
        ):
            continue
        out.append(token)
    return tuple(out)


def _is_disabled() -> bool:
    return os.environ.get("AUTH_DISABLED") == "1"


def _allowed_keys() -> tuple[str, ...]:
    """Return the configured API-key allowlist, refreshed per call.

    Reading from ``os.environ`` on every call (rather than caching at
    import time) lets tests monkeypatch the environment and pick up
    new values without re-importing the module.
    """
    return _parse_keys(os.environ.get("FINRISK_API_KEYS"))


def _matches(provided: str, allowlist: Iterable[str]) -> bool:
    """Constant-time compare ``provided`` against each candidate."""
    return any(secrets.compare_digest(provided, candidate) for candidate in allowlist)


async def require_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> str:
    """FastAPI dependency that enforces the ``X-API-Key`` header.

    Returns the matched key on success; raises 401 on failure. When
    ``AUTH_DISABLED=1`` the dependency returns the literal string
    ``"disabled"`` without inspecting the header.
    """
    if _is_disabled():
        return "disabled"

    allowlist = _allowed_keys()
    if not allowlist:
        # Fail closed: an empty allowlist means auth is unconfigured,
        # not "no auth required". This prevents an accidentally empty
        # ``FINRISK_API_KEYS=`` env var from silently disabling auth.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API auth not configured (set FINRISK_API_KEYS or AUTH_DISABLED=1).",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header.",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    if not _matches(x_api_key, allowlist):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key.",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    return x_api_key


__all__ = ["require_api_key"]
