"""Path interpreter.

Turns the top-ranked :class:`CandidateGraphPath` rows into
:class:`GraphInsightV16` rows. The interpreter is intentionally
deterministic (template-based) for v16; an LLM-based interpreter
can swap in later because every insight it produces must satisfy
the same :class:`GraphInsightV16` schema.
"""

from __future__ import annotations

from src.graph_reasoning.evidence_binder import bind_evidence
from src.graph_reasoning.models import (
    CandidateGraphPath,
    GraphInsightV16,
)
from src.schemas.finrisk import FinRiskWorkflowState


_TEMPLATE = (
    "{source} depends on {intermediate} located in {tail}. The exposure to "
    "{tail_label} creates a {confidence_pct}% probability of supply disruption."
)


def _confidence_label(confidence: float) -> str:
    return f"{round(confidence * 100)}"


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
        explanation = _TEMPLATE.format(
            source=source,
            intermediate=intermediate,
            tail=tail.label,
            tail_label=tail.label,
            confidence_pct=_confidence_label(confidence),
        )
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
                "no LLM judge in v16; explanation is template-based"
            ),
            recommended_next_questions=[
                "Monitor supply diversification announcements from the source company.",
                "Track regional policy changes affecting the intermediate node.",
            ],
            research_theme="supply_chain_exposure",
        )
        insights.append(insight)
    return insights


__all__ = ["interpret_paths"]
