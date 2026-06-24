"""FastAPI app for FinRisk Agent Studio.

Run locally with::

    uvicorn src.api.main:app --reload

The app exposes the workflow routes from :mod:`src.api.workflows`.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI

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

app.include_router(workflows_router)


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
        ],
    }


__all__ = ["app"]