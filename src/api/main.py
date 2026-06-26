"""FastAPI app for FinRisk Agent Studio.

Run locally with::

    uvicorn src.api.main:app --reload

The app exposes the v17 workflow routes from
:mod:`src.api.workflows` and the v18 supply chain routes from
:mod:`src.api.supply_chain`.
"""

from __future__ import annotations

import logging

from fastapi import Depends, FastAPI

from src.api.auth import require_api_key
from src.api.rate_limit import RateLimitMiddleware, build_default_limiter
from src.api.supply_chain import router as supply_chain_router
from src.api.workflows import router as workflows_router

logger = logging.getLogger(__name__)

app = FastAPI(
    title="FinRisk Agent Studio",
    version="0.1.0",
    description=(
        "AI-native financial risk intelligence workflow using local LLMs, "
        "structured outputs, SEC filings, browser exploration, and graph-"
        "based reasoning."
    ),
)

# R1 (supplement): per-key / per-IP rate limiting. The middleware runs
# before the ``Depends(require_api_key)`` resolution, which is fine —
# 401s are still subject to the budget and an attacker cannot amplify
# load on the LLM by hammering unauthenticated requests. Set
# ``RATE_LIMIT_DISABLED=1`` to opt out (e.g. handler-direct tests).
#
# The limiter is rebuilt lazily on every request via :func:`get_limiter`
# so tests that ``monkeypatch.setenv("RATE_LIMIT_RPM", ...)`` see the
# new value without re-importing. The cache is busted by
# :func:`reset_rate_limiter_for_tests`; for tests that only need
# ``RATE_LIMIT_DISABLED=1`` no reset is required.
_limiter_cache: SlidingWindowLimiter | None = None


def get_limiter() -> SlidingWindowLimiter:
    global _limiter_cache
    if _limiter_cache is None:
        _limiter_cache = build_default_limiter()
    return _limiter_cache


def reset_rate_limiter_for_tests() -> None:
    """Drop the cached limiter and reset its buckets. Test-only helper."""
    global _limiter_cache
    _limiter_cache = None


from src.api.rate_limit import SlidingWindowLimiter  # noqa: E402

app.add_middleware(RateLimitMiddleware, get_limiter=get_limiter)

# R1: every workflow / supply-chain route is gated by ``X-API-Key``,
# enforced through a single FastAPI dependency. Set ``AUTH_DISABLED=1``
# to opt out (e.g. local development, internal handler-direct tests).
app.include_router(
    workflows_router,
    dependencies=[Depends(require_api_key)],
)
app.include_router(
    supply_chain_router,
    dependencies=[Depends(require_api_key)],
)


@app.get("/")
async def root() -> dict:
    """Service metadata."""
    return {
        "name": "FinRisk Agent Studio",
        "version": "0.1.0",
        "endpoints": [
            "/workflows/health",
            "/workflows/finrisk/run",
            "/workflows/{run_id}",
            "/workflows/{run_id}/report",
            "/supply-chain/explore",
            "/supply-chain/expand",
            "/supply-chain/{run_id}",
            "/supply-chain/{run_id}/sankey",
        ],
    }


__all__ = ["app"]