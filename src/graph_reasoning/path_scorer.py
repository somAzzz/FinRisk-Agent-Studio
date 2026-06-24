"""Path scorer.

Implements the v16 scoring formula:

```
path_score = 0.25 * evidence_coverage
           + 0.20 * min_edge_confidence
           + 0.20 * relevance_to_analysis_goal
           + 0.15 * source_quality
           + 0.10 * novelty
           + 0.10 * graph_centrality
           - 0.05 * hub_penalty
```

The score is clamped to ``[0, 1]`` and stored on the path along
with the per-component breakdown.
"""

from __future__ import annotations

from collections import Counter

from src.graph_reasoning.models import CandidateGraphPath, GraphQueryContext
from src.schemas.finrisk import FinRiskWorkflowState


def _normalise(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def _keyword_overlap(a: str, b: str) -> float:
    tokens_a = {tok.lower() for tok in a.split() if len(tok) > 3}
    tokens_b = {tok.lower() for tok in b.split() if len(tok) > 3}
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / len(tokens_a)


def score_path(
    path: CandidateGraphPath,
    context: GraphQueryContext,
    state: FinRiskWorkflowState,
) -> CandidateGraphPath:
    """Compute ``path_score`` and ``score_breakdown`` for a path.

    The function returns a *new* :class:`CandidateGraphPath` with
    the score fields populated; the input is left untouched so the
    retriever's output can be cached and re-scored cheaply.
    """
    if not path.edges:
        return path.model_copy(
            update={"path_score": 0.0, "score_breakdown": {}}
        )

    # evidence_coverage: fraction of edges with at least one evidence id.
    evidence_count = sum(1 for e in path.edges if e.metadata.evidence_ids)
    evidence_coverage = evidence_count / len(path.edges)

    # min_edge_confidence: weakest link in the path.
    min_conf = min(e.metadata.confidence for e in path.edges)

    # relevance_to_analysis_goal: lexical overlap with the goal.
    relevance = _keyword_overlap(
        " ".join(n.label for n in path.nodes),
        state.request.analysis_goal,
    )

    # source_quality: average credibility of cited evidence rows.
    cited_evidence = {
        eid
        for e in path.edges
        for eid in e.metadata.evidence_ids
    }
    cited_rows = [
        ev for ev in state.normalized_evidence if ev.evidence_id in cited_evidence
    ]
    if cited_rows:
        source_quality = sum(
            ev.credibility_score or 0.0 for ev in cited_rows
        ) / len(cited_rows)
    else:
        source_quality = 0.0

    # novelty: at least one edge references a non-filing source.
    novelty = 0.0
    for e in path.edges:
        for eid in e.metadata.evidence_ids:
            ev = next(
                (er for er in state.normalized_evidence if er.evidence_id == eid),
                None,
            )
            if ev and ev.source_type in {"web", "transcript", "graph"}:
                novelty = 1.0
                break
        if novelty == 1.0:
            break

    # graph_centrality: simple degree proxy (more edges out of a
    # node means more "central" in this toy graph).
    degrees: Counter[str] = Counter()
    for e in path.edges:
        degrees[e.source_node_id] += 1
    if degrees:
        graph_centrality = min(1.0, max(degrees.values()) / 3.0)
    else:
        graph_centrality = 0.0

    # hub_penalty: penalise paths that revisit a node label.
    labels = [n.label for n in path.nodes]
    hub_penalty = 0.0
    for label, count in Counter(labels).items():
        if count > 1:
            hub_penalty += 0.1 * (count - 1)
    hub_penalty = min(0.5, hub_penalty)

    breakdown = {
        "evidence_coverage": round(evidence_coverage, 4),
        "min_edge_confidence": round(min_conf, 4),
        "relevance": round(relevance, 4),
        "source_quality": round(source_quality, 4),
        "novelty": round(novelty, 4),
        "graph_centrality": round(graph_centrality, 4),
        "hub_penalty": round(hub_penalty, 4),
    }
    raw = (
        0.25 * evidence_coverage
        + 0.20 * min_conf
        + 0.20 * relevance
        + 0.15 * source_quality
        + 0.10 * novelty
        + 0.10 * graph_centrality
        - 0.05 * hub_penalty
    )
    score = _normalise(round(raw, 4))
    return path.model_copy(
        update={"path_score": score, "score_breakdown": breakdown}
    )


def rank_paths(
    paths: list[CandidateGraphPath],
    context: GraphQueryContext,
    state: FinRiskWorkflowState,
) -> list[CandidateGraphPath]:
    """Score every path and return them sorted by score desc."""
    scored = [score_path(p, context, state) for p in paths]
    scored.sort(key=lambda p: p.path_score or 0.0, reverse=True)
    return scored


__all__ = ["rank_paths", "score_path"]
