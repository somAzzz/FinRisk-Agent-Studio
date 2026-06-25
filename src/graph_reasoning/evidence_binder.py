"""Evidence binder.

Resolves the path's edge-level evidence ids against the
state's normalized evidence. The binder is the bridge between
the graph subsystem (which only knows edge metadata) and the
report subsystem (which only knows ``NormalizedEvidence``).
"""

from __future__ import annotations

from src.graph_reasoning.models import CandidateGraphPath
from src.schemas.finrisk import FinRiskWorkflowState, NormalizedEvidence


def bind_evidence(
    path: CandidateGraphPath,
    state: FinRiskWorkflowState,
) -> tuple[list[NormalizedEvidence], list[str]]:
    """Return ``(resolved_evidence_rows, hypothesis_edge_ids)``.

    The first list is the unique set of normalized evidence rows
    that back the path. The second list is the ids of edges whose
    evidence could not be resolved; those edges are considered
    *hypothesis edges* by the rest of the v16 pipeline.
    """
    by_id = {ev.evidence_id: ev for ev in state.normalized_evidence}
    resolved: dict[str, NormalizedEvidence] = {}
    hypothesis: list[str] = []
    for edge in path.edges:
        if not edge.metadata.evidence_ids:
            hypothesis.append(edge.edge_id)
            continue
        any_resolved = False
        for eid in edge.metadata.evidence_ids:
            if eid in by_id:
                resolved[eid] = by_id[eid]
                any_resolved = True
        if not any_resolved:
            hypothesis.append(edge.edge_id)
    return list(resolved.values()), hypothesis


__all__ = ["bind_evidence"]
