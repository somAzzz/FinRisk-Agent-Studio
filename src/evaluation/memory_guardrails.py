"""Guardrails for writing evidence and graph records into memory."""

from __future__ import annotations

from src.memory.models import MemoryItem, MemoryStatus, MemoryWriteDecision
from src.supply_chain.models import SupplyChainEdge


class MemoryWriteGuardrails:
    """Validate a MemoryItem before it is written to long-lived memory."""

    name = "memory_write_guardrails"

    def validate(self, item: MemoryItem) -> MemoryWriteDecision:
        """Return whether the item may be written, with optional status downgrade."""
        reasons: list[str] = []
        target_status: MemoryStatus | None = None

        if item.claim_type == "hypothesis" and item.status == "active":
            target_status = "candidate"
            reasons.append("hypothesis_memory_downgraded_to_candidate")

        if item.source_type in {"web", "news"} and item.status == "active":
            target_status = "candidate"
            reasons.append("untrusted_web_memory_downgraded_to_candidate")

        if item.provenance.get("extracted_by") == "llm" and item.status == "active":
            target_status = "candidate"
            reasons.append("llm_extracted_memory_downgraded_to_candidate")

        if item.source_type in {"web", "news", "company", "regulatory"} and not item.source_url:
            reasons.append("source_url_missing")

        if item.memory_type == "domain_prior" and item.claim_type == "evidence":
            return MemoryWriteDecision(
                memory_id=item.memory_id,
                allowed=False,
                target_status=None,
                reasons=["domain_prior_cannot_be_evidence"],
            )

        return MemoryWriteDecision(
            memory_id=item.memory_id,
            allowed=True,
            target_status=target_status,
            reasons=reasons,
        )


class GraphMemoryGuardrails:
    """Validate graph edge memory before persistence."""

    name = "graph_memory_guardrails"

    def validate_edge(self, edge: SupplyChainEdge) -> MemoryWriteDecision:
        """Validate a v18 supply-chain edge before graph-memory write."""
        reasons: list[str] = []
        if edge.relation_type != "hypothesized" and not edge.evidence_ids:
            return MemoryWriteDecision(
                memory_id=f"mem:graph-edge:{edge.edge_id}",
                allowed=False,
                reasons=["confirmed_edge_missing_evidence"],
            )
        if edge.relation_type == "hypothesized":
            reasons.append("hypothesis_edge_written_as_candidate")
            return MemoryWriteDecision(
                memory_id=f"mem:graph-edge:{edge.edge_id}",
                allowed=True,
                target_status="candidate",
                reasons=reasons,
            )
        return MemoryWriteDecision(
            memory_id=f"mem:graph-edge:{edge.edge_id}",
            allowed=True,
            target_status="active",
            reasons=reasons,
        )


__all__ = ["GraphMemoryGuardrails", "MemoryWriteGuardrails"]
