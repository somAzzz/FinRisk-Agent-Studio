"""Executable safety gate for Pydantic Graph parallel branches."""

from __future__ import annotations

from dataclasses import dataclass


class UnsafeParallelPlanError(ValueError):
    """Raised when branches have data dependencies or shared writes."""


@dataclass(frozen=True, slots=True)
class NodeAccess:
    """Declared canonical-state reads and writes for one graph node."""

    node_id: str
    reads: frozenset[str]
    writes: frozenset[str]


def validate_parallel_group(nodes: list[NodeAccess]) -> None:
    """Reject read-after-write, write-after-read and shared-write races."""
    conflicts: list[str] = []
    for index, left in enumerate(nodes):
        for right in nodes[index + 1 :]:
            shared_writes = left.writes & right.writes
            left_to_right = left.writes & right.reads
            right_to_left = right.writes & left.reads
            fields = shared_writes | left_to_right | right_to_left
            if fields:
                conflicts.append(
                    f"{left.node_id}<->{right.node_id}:"
                    + ",".join(sorted(fields))
                )
    if conflicts:
        raise UnsafeParallelPlanError("; ".join(conflicts))


FINRISK_PARALLEL_CANDIDATES = [
    NodeAccess(
        node_id="filing_risk_extractor",
        reads=frozenset({"company", "request"}),
        writes=frozenset({"filing_risks", "chunk_validations", "llm_log"}),
    ),
    NodeAccess(
        node_id="market_explorer",
        reads=frozenset({"company", "request", "filing_risks"}),
        writes=frozenset({"market_evidence", "tool_traces", "llm_log"}),
    ),
]


__all__ = [
    "FINRISK_PARALLEL_CANDIDATES",
    "NodeAccess",
    "UnsafeParallelPlanError",
    "validate_parallel_group",
]
