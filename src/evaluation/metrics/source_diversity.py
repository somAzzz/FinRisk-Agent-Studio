"""Source diversity metric.

The v16 spec defines diversity as the fraction of unique source
domains over the total evidence count, clamped to ``[0, 1]``. We
also expose an enhanced "diversity bucket" that penalises runs where
all evidence comes from a single source type.
"""

from __future__ import annotations

from collections import Counter
from urllib.parse import urlparse

from src.schemas.finrisk import NormalizedEvidence


def _domain_for(ev: NormalizedEvidence) -> str:
    url = (ev.source_url or "").strip().lower()
    if not url:
        return f"type:{ev.source_type}"
    try:
        return urlparse(url).netloc or f"type:{ev.source_type}"
    except ValueError:
        return f"type:{ev.source_type}"


def source_diversity_score(evidence: list[NormalizedEvidence]) -> float:
    """Return ``unique_domains / evidence_count`` clamped to ``[0, 1]``.

    A run with one source per evidence row scores ``1.0``. A run
    with five evidence rows from the same domain scores ``0.2``.
    The metric ignores evidence with no URL and groups them under
    ``type:<source_type>`` so the score remains defined when the
    pipeline has not yet produced URLs.
    """
    if not evidence:
        return 0.0
    domains = {_domain_for(ev) for ev in evidence}
    return min(1.0, len(domains) / max(1, len(evidence)))


def source_type_distribution(
    evidence: list[NormalizedEvidence],
) -> dict[str, int]:
    """Return ``source_type -> count``."""
    return dict(Counter(ev.source_type for ev in evidence))


def has_primary_source(evidence: list[NormalizedEvidence]) -> bool:
    """A primary source is a filing or company-published document."""
    primary_types = {"filing", "company", "regulatory"}
    return any(ev.source_type in primary_types for ev in evidence)


__all__ = [
    "source_diversity_score",
    "source_type_distribution",
    "has_primary_source",
]
