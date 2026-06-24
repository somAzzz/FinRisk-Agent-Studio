"""Graph context builder.

Translates the v15 ``FinRiskWorkflowState`` (company + risks + goal)
into a :class:`GraphQueryContext` that the path retriever consumes.
The builder is a pure function: no I/O, no LLM.
"""

from __future__ import annotations

from src.graph_reasoning.models import GraphQueryContext
from src.schemas.finrisk import FinRiskWorkflowState

_RISK_TYPE_TO_EDGE_TYPES: dict[str, list[str]] = {
    "supply_chain": ["SUPPLIES", "LOCATED_IN", "EXPOSED_TO", "DEPENDS_ON"],
    "policy": ["REGULATED_BY", "EXPOSED_TO", "AFFECTS"],
    "geopolitical": ["LOCATED_IN", "EXPOSED_TO", "AFFECTS"],
    "regulatory": ["REGULATED_BY", "EXPOSED_TO"],
    "operational": ["DEPENDS_ON", "SUPPLIES"],
    "competition": ["COMPETES_WITH", "AFFECTS"],
    "macro": ["EXPOSED_TO", "AFFECTS"],
    "climate": ["EXPOSED_TO", "LOCATED_IN", "AFFECTS"],
    "technology": ["DEPENDS_ON", "AFFECTS"],
    "financial": ["AFFECTS", "EXPOSED_TO"],
}


# Default edge types when the state has no filing risks. The
# fixture graph uses these so the demo workflow always returns a
# few candidate paths even for "company only" contexts.
_DEFAULT_EDGE_TYPES: tuple[str, ...] = (
    "DEPENDS_ON",
    "LOCATED_IN",
    "EXPOSED_TO",
    "AFFECTS",
    "ISSUES",
)


def build_graph_context(state: FinRiskWorkflowState) -> GraphQueryContext:
    """Produce a :class:`GraphQueryContext` for the current state."""
    ticker = state.request.ticker
    company_id = f"company:{ticker}"
    risk_ids = [r.risk_id for r in state.filing_risks]
    risk_types = sorted({r.risk_type for r in state.filing_risks})
    allowed_edge_types: set[str] = set()
    for rt in risk_types:
        for edge_type in _RISK_TYPE_TO_EDGE_TYPES.get(rt, []):
            allowed_edge_types.add(edge_type)
    if not allowed_edge_types:
        # No filing risks → fall back to the default set so the
        # retriever still produces paths.
        allowed_edge_types.update(_DEFAULT_EDGE_TYPES)
    # Always include the basic "AFFECTS" edge so paths can return to
    # the company node.
    allowed_edge_types.add("AFFECTS")
    focus_entities: list[str] = []
    if state.company is not None:
        focus_entities.append(state.company.company_name)
    focus_entities.extend(risk_types)
    return GraphQueryContext(
        company_id=company_id,
        ticker=ticker,
        risk_ids=risk_ids,
        focus_entities=focus_entities,
        focus_risk_types=risk_types,
        max_hops=3,
        allowed_edge_types=sorted(allowed_edge_types),
    )


__all__ = ["build_graph_context"]
