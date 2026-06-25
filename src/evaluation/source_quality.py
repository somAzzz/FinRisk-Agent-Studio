"""v16 SourceQuality model + scoring helpers.

The model captures the three orthogonal dimensions called out in
the v16 spec: ``credibility_score`` (how much do we trust the
publisher), ``freshness_score`` (how recent is the data), and
``relevance_score`` (how on-topic is the source for the
analysis_goal). ``is_primary_source`` is a convenience flag for
the diversity guardrail.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.workflows.state import utcnow

SourceType = Literal[
    "filing",
    "regulatory",
    "company",
    "financial_news",
    "general_news",
    "blog",
    "unknown",
]


# v16 default credibility scores. The first six keys are the v16
# categories; the remaining entries map the v15 NormalizedSourceType
# values ("web", "transcript", "graph", "fixture") into the same
# scale so the validator can consume existing evidence rows without
# any schema migration.
DEFAULT_CREDIBILITY: dict[str, float] = {
    "filing": 1.0,
    "regulatory": 1.0,
    "company": 0.9,
    "financial_news": 0.8,
    "general_news": 0.6,
    "blog": 0.4,
    "unknown": 0.2,
    "web": 0.6,
    "transcript": 0.8,
    "graph": 0.4,
    "fixture": 0.4,
}


class SourceQuality(BaseModel):
    """A typed quality record for a single evidence row."""

    model_config = ConfigDict(extra="forbid")

    source_url: str
    source_type: SourceType
    credibility_score: float = Field(ge=0.0, le=1.0)
    freshness_score: float = Field(ge=0.0, le=1.0)
    relevance_score: float = Field(ge=0.0, le=1.0)
    is_primary_source: bool


def freshness_from_age(age_days: float | None) -> float:
    """Convert an age in days to a freshness score in ``[0, 1]``.

    The v16 spec uses a piecewise scale: ``1.0`` for ``<= 30`` days,
    ``0.7`` for ``<= 180`` days, ``0.5`` for ``<= 365`` days, and
    ``0.3`` for older or missing timestamps.
    """
    if age_days is None or age_days < 0:
        return 0.3
    if age_days <= 30:
        return 1.0
    if age_days <= 180:
        return 0.7
    if age_days <= 365:
        return 0.5
    return 0.3


def classify_source_type(source_type: str) -> SourceType:
    """Map any string into a v16 source type, defaulting to ``unknown``.

    The function accepts both the v16 categories and the v15
    NormalizedSourceType values (``web``, ``transcript``, ``graph``,
    ``fixture``) so the validator works against existing evidence
    rows without a schema migration.
    """
    if source_type in {"filing", "regulatory", "company"}:
        return source_type  # type: ignore[return-value]
    if source_type in {"web"}:
        return "general_news"
    if source_type in {"transcript"}:
        return "financial_news"
    if source_type in {"graph", "fixture"}:
        return "unknown"
    return "unknown"


_PRIMARY = {"filing", "regulatory", "company"}


def build_source_quality(
    *,
    source_url: str,
    source_type: str,
    collected_at: datetime | None = None,
    relevance_score: float = 0.5,
) -> SourceQuality:
    """Construct a :class:`SourceQuality` from raw evidence metadata."""
    normalised_type = classify_source_type(source_type)
    age_days: float | None = None
    if collected_at is not None:
        if collected_at.tzinfo is None:
            collected_at = collected_at.replace(tzinfo=UTC)
        delta = utcnow() - collected_at
        age_days = max(0.0, delta.total_seconds() / 86400.0)
    return SourceQuality(
        source_url=source_url or "n/a",
        source_type=normalised_type,
        credibility_score=DEFAULT_CREDIBILITY[normalised_type],
        freshness_score=(
            0.7 if normalised_type == "filing" else freshness_from_age(age_days)
        ),
        relevance_score=relevance_score,
        is_primary_source=normalised_type in _PRIMARY,
    )


__all__ = [
    "DEFAULT_CREDIBILITY",
    "SourceQuality",
    "SourceType",
    "build_source_quality",
    "classify_source_type",
    "freshness_from_age",
]
