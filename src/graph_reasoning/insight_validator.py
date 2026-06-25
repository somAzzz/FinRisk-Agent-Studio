"""Insight validator.

Checks each :class:`GraphInsightV16` against the v16 invariants:

- ``risk_path_ids`` reference paths that exist in the candidate list.
- ``affected_entities`` are all labels from the cited paths.
- ``evidence_ids`` reference rows in the state's normalized evidence.
- ``confidence`` is no more than ``max(path_score) + 0.1``.
- the insight references a path of 2-4 hops.
- edges with no evidence are flagged as hypothesis.

The validator emits :class:`GuardrailFinding` records so the
output is consistent with the rest of the v16 quality layer.
"""

from __future__ import annotations

from src.evaluation.models import (
    GuardrailFinding,
    GuardrailSeverity,
    GuardrailStatus,
)
from src.graph_reasoning.evidence_binder import bind_evidence
from src.graph_reasoning.models import (
    CandidateGraphPath,
    GraphInsightV16,
)
from src.schemas.finrisk import FinRiskWorkflowState


def _path_by_id(paths: list[CandidateGraphPath]) -> dict[str, CandidateGraphPath]:
    return {p.path_id: p for p in paths}


def validate_insight(
    insight: GraphInsightV16,
    state: FinRiskWorkflowState,
    paths: list[CandidateGraphPath],
) -> list[GuardrailFinding]:
    findings: list[GuardrailFinding] = []
    by_id = _path_by_id(paths)
    valid_evidence = {ev.evidence_id for ev in state.normalized_evidence}

    for pid in insight.risk_path_ids:
        if pid not in by_id:
            findings.append(
                GuardrailFinding(
                    step_name="graph_reasoner",
                    check_name="graph_path",
                    status=GuardrailStatus.FAIL,
                    severity=GuardrailSeverity.BLOCKER,
                    message=(
                        f"insight {insight.insight_id} references missing path {pid}"
                    ),
                    affected_object_type="graph_path",
                    affected_object_id=pid,
                )
            )
    cited_paths = [by_id[pid] for pid in insight.risk_path_ids if pid in by_id]
    valid_labels = {n.label for p in cited_paths for n in p.nodes}
    for entity in insight.affected_entities:
        if entity not in valid_labels:
            findings.append(
                GuardrailFinding(
                    step_name="graph_reasoner",
                    check_name="graph_path",
                    status=GuardrailStatus.FAIL,
                    severity=GuardrailSeverity.BLOCKER,
                    message=(
                        f"insight {insight.insight_id} affected entity "
                        f"{entity!r} not present in any cited path"
                    ),
                    affected_object_type="graph_path",
                    affected_object_id=insight.insight_id,
                    recommendation="drop or replace the affected entity",
                )
            )
    for eid in insight.evidence_ids:
        if eid not in valid_evidence:
            findings.append(
                GuardrailFinding(
                    step_name="graph_reasoner",
                    check_name="graph_path",
                    status=GuardrailStatus.FAIL,
                    severity=GuardrailSeverity.BLOCKER,
                    message=(
                        f"insight {insight.insight_id} cites missing evidence {eid}"
                    ),
                    affected_object_type="graph_path",
                    affected_object_id=insight.insight_id,
                )
            )

    # Path length 2-4 hops (per spec).
    for path in cited_paths:
        if not (2 <= path.hop_count <= 4):
            findings.append(
                GuardrailFinding(
                    step_name="graph_reasoner",
                    check_name="graph_path",
                    status=GuardrailStatus.FAIL,
                    severity=GuardrailSeverity.BLOCKER,
                    message=(
                        f"path {path.path_id} has {path.hop_count} hops; "
                        "v16 requires 2-4"
                    ),
                    affected_object_type="graph_path",
                    affected_object_id=path.path_id,
                )
            )
        # Hypothesis edges: any path with at least one
        # evidence-less edge gets a warning.
        _, hypothesis_edges = bind_evidence(path, state)
        for edge_id in hypothesis_edges:
            findings.append(
                GuardrailFinding(
                    step_name="graph_reasoner",
                    check_name="graph_path",
                    status=GuardrailStatus.NEEDS_REVIEW,
                    severity=GuardrailSeverity.WARNING,
                    message=(
                        f"path {path.path_id} edge {edge_id} has no evidence; "
                        "treating as hypothesis"
                    ),
                    affected_object_type="graph_path",
                    affected_object_id=path.path_id,
                )
            )

    # Confidence ceiling.
    if cited_paths and insight.confidence > 0:
        max_path_score = max(
            (p.path_score or 0.0) for p in cited_paths
        )
        if insight.confidence > max_path_score + 0.1 + 1e-6:
            findings.append(
                GuardrailFinding(
                    step_name="graph_reasoner",
                    check_name="graph_path",
                    status=GuardrailStatus.NEEDS_REVIEW,
                    severity=GuardrailSeverity.WARNING,
                    message=(
                        f"insight {insight.insight_id} confidence "
                        f"{insight.confidence:.2f} exceeds path_score "
                        f"{max_path_score:.2f} + 0.1; downgrading"
                    ),
                    affected_object_type="graph_path",
                    affected_object_id=insight.insight_id,
                )
            )
            # Downgrade confidence so the warning is actionable.
            insight.confidence = round(max_path_score + 0.1, 4)
    return findings


def validate_all(
    insights: list[GraphInsightV16],
    state: FinRiskWorkflowState,
    paths: list[CandidateGraphPath],
) -> list[GuardrailFinding]:
    out: list[GuardrailFinding] = []
    for insight in insights:
        out.extend(validate_insight(insight, state, paths))
    return out


__all__ = ["validate_all", "validate_insight"]
