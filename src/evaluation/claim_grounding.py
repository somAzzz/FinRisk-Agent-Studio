"""v16 claim grounding models and helpers.

This module is independent of ``src.schemas.claims`` (which is the
project-wide claim primitive used by the extraction pipelines). The
:class:`Claim` here is a lightweight v16 primitive that
``state.claims`` carries during the report-rendering phase.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ClaimType = Literal["evidence", "inference", "hypothesis"]


class Claim(BaseModel):
    """A v16 claim: a typed assertion that points at evidence.

    ``claim_type`` distinguishes three classes:

    - ``evidence`` — direct quote or summary from a primary source.
    - ``inference`` — derived from evidence by a rule.
    - ``hypothesis`` — speculative link, allowed with low confidence.

    Claims with empty ``supporting_evidence_ids`` are treated as
    unsupported by the v16 validators. ``related_risk_ids`` links the
    claim back to the risk object(s) it explains so the full chain is:
    ``risk -> claim -> evidence``.
    """

    model_config = ConfigDict(extra="forbid")

    claim_id: str
    text: str
    claim_type: ClaimType
    related_risk_ids: list[str] = Field(default_factory=list)
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class ClaimGroundingJudgement(BaseModel):
    """Optional LLM/NLI judge verdict (off by default in v16)."""

    model_config = ConfigDict(extra="forbid")

    claim_id: str
    verdict: Literal[
        "supported", "partially_supported", "unsupported", "contradicted"
    ]
    explanation: str
    missing_evidence: str | None = None


# ---------------------------------------------------------------------------
# Lexical overlap grounding (Layer 2)
# ---------------------------------------------------------------------------


_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]+")
_STOPWORDS: frozenset[str] = frozenset(
    {
        "the", "a", "an", "and", "or", "but", "of", "to", "in", "on",
        "for", "with", "by", "from", "as", "is", "are", "was", "were",
        "be", "been", "being", "this", "that", "these", "those", "it",
        "its", "have", "has", "had", "do", "does", "did", "will",
        "would", "could", "should", "may", "might", "must", "shall",
        "into", "than", "then", "so", "if", "not", "no", "any", "all",
        "some", "such", "their", "they", "them", "we", "us", "our",
        "you", "your", "he", "she", "his", "her", "at", "i", "ii",
        "iii", "iv", "v", "vi", "vii", "viii", "ix", "x",
    }
)


def _tokenise(text: str) -> set[str]:
    return {tok.lower() for tok in _TOKEN_RE.findall(text or "")} - _STOPWORDS


def lexical_overlap(claim_text: str, evidence_text: str) -> float:
    """Return ``|claim ∩ evidence| / |claim|`` as a float in ``[0, 1]``.

    The function is intentionally simple — it gives a deterministic
    proxy for "is this claim grounded in the cited evidence?". A
    value of ``0`` means there is no lexical overlap at all; ``1``
    means every claim token appears in the evidence.
    """
    claim_tokens = _tokenise(claim_text)
    if not claim_tokens:
        return 0.0
    evidence_tokens = _tokenise(evidence_text)
    if not evidence_tokens:
        return 0.0
    return len(claim_tokens & evidence_tokens) / len(claim_tokens)


def grounding_label(overlap: float) -> Literal[
    "grounded", "needs_review", "unsupported"
]:
    """Translate an overlap score into a v16 label."""
    if overlap >= 0.25:
        return "grounded"
    if overlap >= 0.10:
        return "needs_review"
    return "unsupported"


__all__ = [
    "Claim",
    "ClaimGroundingJudgement",
    "ClaimType",
    "grounding_label",
    "lexical_overlap",
]
