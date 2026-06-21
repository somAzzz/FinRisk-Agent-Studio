"""Graph-level evaluation: duplicate entities, orphan evidence, query health.

These metrics are computed from lightweight data structures rather than
requiring a live Neo4j connection, so the evaluation can run in CI.

Inputs:
- ``graph_writer_calls``: a list of call-summary objects, each expected
  to expose ``.entity_id`` (or ``entity_ids``) and ``.evidence_ids``
  (or ``.evidence_id``) attributes.
- ``query_results``: a list of booleans indicating whether each query
  succeeded.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field


class _GraphCallLike(Protocol):
    """Duck-typed shape of a single ``GraphWriter`` call summary.

    Either ``entity_id`` (for a single write) or ``entity_ids`` (for a
    bulk write) may be supplied. The same is true for evidence ids.
    """

    entity_id: str | None
    entity_ids: Iterable[str] | None
    evidence_id: str | None
    evidence_ids: Iterable[str] | None


class GraphEvalResult(BaseModel):
    """Aggregate metrics for a knowledge-graph write batch."""

    model_config = ConfigDict(extra="forbid")

    duplicate_entity_rate: float = Field(ge=0.0, le=1.0)
    relation_without_evidence_count: int = Field(ge=0)
    orphan_evidence_count: int = Field(ge=0)
    query_success_rate: float = Field(ge=0.0, le=1.0)
    total_entities: int = Field(ge=0)
    total_evidence: int = Field(ge=0)
    total_queries: int = Field(ge=0)


def _entity_ids_for(call: Any) -> list[str]:
    """Return the entity ids touched by a graph write call, normalised."""
    ids: list[str] = []
    single = getattr(call, "entity_id", None)
    if isinstance(single, str) and single:
        ids.append(single)
    many = getattr(call, "entity_ids", None)
    if many is not None:
        ids.extend(str(e) for e in many if e)
    return ids


def _evidence_ids_for(call: Any) -> list[str]:
    """Return the evidence ids touched by a graph write call, normalised."""
    ids: list[str] = []
    single = getattr(call, "evidence_id", None)
    if isinstance(single, str) and single:
        ids.append(single)
    many = getattr(call, "evidence_ids", None)
    if many is not None:
        ids.extend(str(e) for e in many if e)
    return ids


def evaluate_graph(
    graph_writer_calls: list,
    query_results: list[bool],
) -> GraphEvalResult:
    """Compute graph-write quality metrics from a batch of calls."""
    entity_seen: dict[str, int] = {}
    evidence_seen: set[str] = set()
    total_entities = 0
    total_evidence = 0

    for call in graph_writer_calls:
        for eid in _entity_ids_for(call):
            entity_seen[eid] = entity_seen.get(eid, 0) + 1
            total_entities += 1
        for ev_id in _evidence_ids_for(call):
            evidence_seen.add(ev_id)
            total_evidence += 1

    duplicates = sum(c - 1 for c in entity_seen.values() if c > 1)
    total_unique_entities = max(1, len(entity_seen))
    duplicate_rate = duplicates / total_unique_entities

    # A relation-without-evidence count requires the call summaries to
    # expose ``relation_ids`` and ``has_evidence`` flags. When those are
    # not present we conservatively report zero.
    relation_without_evidence = 0
    for call in graph_writer_calls:
        rel_ids = list(getattr(call, "relation_ids", []) or [])
        has_evidence = bool(
            getattr(call, "has_evidence", False)
            or _evidence_ids_for(call)
        )
        if rel_ids and not has_evidence:
            relation_without_evidence += len(rel_ids)

    # Orphan evidence: written but never linked to any entity or claim.
    # The current call summaries do not capture this, so we report zero.
    orphan_evidence = 0

    total_queries = len(query_results)
    if total_queries:
        successes = sum(1 for r in query_results if r)
        query_rate = successes / total_queries
    else:
        query_rate = 1.0

    return GraphEvalResult(
        duplicate_entity_rate=round(duplicate_rate, 4),
        relation_without_evidence_count=relation_without_evidence,
        orphan_evidence_count=orphan_evidence,
        query_success_rate=round(query_rate, 4),
        total_entities=total_entities,
        total_evidence=total_evidence,
        total_queries=total_queries,
    )


__all__ = ["GraphEvalResult", "evaluate_graph"]
