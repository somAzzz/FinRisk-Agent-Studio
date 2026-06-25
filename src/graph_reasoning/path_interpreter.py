"""Path interpreter.

Turns the top-ranked :class:`CandidateGraphPath` rows into
:class:`GraphInsightV16` rows. The interpreter is intentionally
deterministic (template-based) for v16; an LLM-based interpreter
can swap in later because every insight it produces must satisfy
the same :class:`GraphInsightV16` schema.

v17 safety constraints
----------------------

The interpreter never emits language that could be misread as a
financial forecast or investment recommendation. Forbidden
phrases (see ``_FORBIDDEN_PHRASES``) are filtered out of the
template output, and the template itself avoids the words
"probability", "guaranteed", "buy", "sell", and "should invest".

All "market opportunity" insights are emitted as
``research_theme`` only — the legacy ``investment_theme`` field
is not produced.
"""

from __future__ import annotations

import re

from src.graph_reasoning.evidence_binder import bind_evidence
from src.graph_reasoning.models import (
    CandidateGraphPath,
    GraphInsightV16,
)
from src.schemas.finrisk import FinRiskWorkflowState

_TEMPLATE = (
    "This path suggests a plausible exposure channel: {source} connects to "
    "{tail} via {intermediate}. Path score is {confidence_label} (research "
    "hypothesis, not a financial impact forecast). It does not prove "
    "immediate financial impact and should be treated as a research prompt."
)


_FORBIDDEN_PHRASES: tuple[str, ...] = (
    "probability",
    "guaranteed",
    "guarantee",
    "strong buy",
    "strong sell",
    "buy now",
    "sell now",
    "must invest",
    "should invest",
    "稳赚",
    "保证",
    "买入",
    "卖出",
)


_FORBIDDEN_RE: tuple[re.Pattern[str], ...] = tuple(
    re.compile(rf"\b{re.escape(phrase)}\b", re.IGNORECASE)
    for phrase in _FORBIDDEN_PHRASES
)


def _confidence_label(confidence: float) -> str:
    return f"{round(confidence * 100)}%"


def _scrub(text: str) -> str:
    """Remove forbidden phrases from the template output.

    The scrubber replaces matches with ``[REDACTED]`` so the rest
    of the sentence stays readable. It is case-insensitive and
    uses word boundaries so partial matches ("guaranteed" inside
    "guaranteedly") are also caught.
    """
    out = text
    for pattern in _FORBIDDEN_RE:
        out = pattern.sub("[REDACTED]", out)
    return out


def interpret_paths(
    paths: list[CandidateGraphPath],
    state: FinRiskWorkflowState,
    *,
    top_k: int = 1,
) -> list[GraphInsightV16]:
    """Convert up to ``top_k`` paths into v16 insights."""
    ranked = sorted(
        paths, key=lambda p: p.path_score or 0.0, reverse=True
    )[:top_k]
    insights: list[GraphInsightV16] = []
    for path in ranked:
        if len(path.nodes) < 2:
            continue
        company = state.company.company_name if state.company else state.request.ticker
        source = path.nodes[0].label
        tail = path.nodes[-1]
        intermediate = path.nodes[1].label if len(path.nodes) > 2 else "its supply chain"
        confidence = path.path_score or 0.0
        raw_explanation = _TEMPLATE.format(
            source=source,
            intermediate=intermediate,
            tail=tail.label,
            confidence_label=_confidence_label(confidence),
        )
        explanation = _scrub(raw_explanation)
        resolved_evidence, _ = bind_evidence(path, state)
        insight = GraphInsightV16(
            source_company=company,
            insight_type="second_order_risk",
            risk_path_ids=[path.path_id],
            affected_entities=[tail.label],
            explanation=explanation,
            evidence_ids=[ev.evidence_id for ev in resolved_evidence],
            confidence=confidence,
            uncertainty=(
                "no LLM judge in v16; explanation is template-based and "
                "scrubbed against the v17 financial-advice blocklist"
            ),
            recommended_next_questions=[
                "Monitor supply diversification announcements from the source company.",
                "Track regional policy changes affecting the intermediate node.",
            ],
            research_theme="supply_chain_exposure",
        )
        insights.append(insight)
    return insights


__all__ = ["_FORBIDDEN_PHRASES", "_scrub", "interpret_paths"]
