"""Adapters from existing project evidence/graph schemas into MemoryItem."""

from __future__ import annotations

from typing import Any

from src.memory.models import MemoryItem, MemorySourceType
from src.schemas.evidence import Evidence
from src.supply_chain.models import NormalizedSupplyChainEvidence, SupplyChainEdge


def memory_item_from_evidence(
    evidence: Evidence,
    *,
    run_id: str | None = None,
    status: str | None = None,
) -> MemoryItem:
    """Convert canonical project Evidence into a MemoryItem."""
    source_type = _map_evidence_source_type(evidence.source_type)
    memory_status = status or _default_status_for_source(source_type)
    return MemoryItem(
        memory_id=f"mem:evidence:{evidence.evidence_id}",
        memory_type="evidence",
        text=evidence.quote,
        summary=evidence.metadata.get("summary"),
        source_type=source_type,
        source_url=evidence.url,
        source_title=evidence.title,
        entities=_list_metadata(evidence.metadata, "entities"),
        tickers=_list_metadata(evidence.metadata, "tickers"),
        products=_list_metadata(evidence.metadata, "products"),
        risks=_list_metadata(evidence.metadata, "risks"),
        published_at=evidence.published_at,
        retrieved_at=evidence.retrieved_at,
        credibility_score=_credibility_for_source(source_type),
        freshness_score=1.0,
        confidence=evidence.confidence,
        claim_type="evidence",
        status=memory_status,  # type: ignore[arg-type]
        provenance={
            "kind": "Evidence",
            "evidence_id": evidence.evidence_id,
            "source_id": evidence.source_id,
            "section": evidence.section,
            "speaker": evidence.speaker,
            "run_id": run_id,
            "metadata": evidence.metadata,
        },
    )


def memory_item_from_supply_chain_evidence(
    evidence: NormalizedSupplyChainEvidence,
    *,
    run_id: str | None = None,
    status: str | None = None,
) -> MemoryItem:
    """Convert v18 supply-chain evidence into a MemoryItem."""
    source_type = _map_supply_chain_source_type(evidence.source_type)
    memory_status = status or _default_status_for_source(source_type)
    return MemoryItem(
        memory_id=f"mem:supply-evidence:{evidence.evidence_id}",
        memory_type="evidence",
        text=evidence.quote,
        summary=evidence.summary,
        source_type=source_type,
        source_url=evidence.url,
        source_title=evidence.title,
        published_at=evidence.published_at,
        retrieved_at=evidence.retrieved_at,
        credibility_score=_credibility_for_source(source_type),
        freshness_score=1.0,
        confidence=evidence.confidence,
        claim_type="evidence",
        status=memory_status,  # type: ignore[arg-type]
        provenance={
            "kind": "NormalizedSupplyChainEvidence",
            "evidence_id": evidence.evidence_id,
            "source_name": evidence.source_name,
            "run_id": run_id,
            "metadata": evidence.metadata,
        },
    )


def memory_item_from_supply_chain_edge(
    edge: SupplyChainEdge,
    *,
    run_id: str | None = None,
    status: str | None = None,
) -> MemoryItem:
    """Convert a v18 supply-chain edge into graph-edge memory."""
    is_hypothesis = edge.relation_type == "hypothesized"
    claim_type = "hypothesis" if is_hypothesis else "evidence"
    memory_status = status or ("candidate" if is_hypothesis else "active")
    text = (
        f"{edge.source_node_id} {edge.relation_type} {edge.target_node_id} "
        f"(confidence={edge.confidence:.2f})"
    )
    return MemoryItem(
        memory_id=f"mem:graph-edge:{edge.edge_id}",
        memory_type="graph_edge",
        text=text,
        summary=text,
        source_type="graph",
        entities=[edge.source_node_id, edge.target_node_id],
        credibility_score=edge.confidence if not is_hypothesis else min(0.5, edge.confidence),
        freshness_score=1.0,
        confidence=edge.confidence,
        claim_type=claim_type,
        status=memory_status,  # type: ignore[arg-type]
        provenance={
            "kind": "SupplyChainEdge",
            "edge": edge.model_dump(mode="json"),
            "edge_id": edge.edge_id,
            "source_node_id": edge.source_node_id,
            "target_node_id": edge.target_node_id,
            "relation_type": edge.relation_type,
            "evidence_ids": list(edge.evidence_ids),
            "run_id": run_id,
        },
    )


def _map_evidence_source_type(source_type: str) -> MemorySourceType:
    mapping: dict[str, MemorySourceType] = {
        "edgar_corpus": "filing",
        "sec_filing": "filing",
        "sec_xbrl": "filing",
        "transcript": "transcript",
        "web": "web",
        "browser": "web",
        "manual": "manual",
    }
    return mapping.get(source_type, "web")


def _map_supply_chain_source_type(source_type: str) -> MemorySourceType:
    mapping: dict[str, MemorySourceType] = {
        "web": "web",
        "filing": "filing",
        "transcript": "transcript",
        "company": "company",
        "manual": "manual",
        "fixture": "fixture",
    }
    return mapping.get(source_type, "web")


def _default_status_for_source(source_type: MemorySourceType) -> str:
    if source_type in {"filing", "company", "regulatory", "fixture"}:
        return "active"
    return "candidate"


def _credibility_for_source(source_type: MemorySourceType) -> float:
    scores: dict[MemorySourceType, float] = {
        "filing": 0.95,
        "company": 0.9,
        "regulatory": 0.95,
        "transcript": 0.85,
        "fixture": 0.8,
        "web": 0.65,
        "news": 0.7,
        "graph": 0.75,
        "domain_prior": 0.4,
        "human_feedback": 1.0,
        "manual": 0.7,
    }
    return scores[source_type]


def _list_metadata(metadata: dict[str, Any], key: str) -> list[str]:
    value = metadata.get(key)
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


__all__ = [
    "memory_item_from_evidence",
    "memory_item_from_supply_chain_edge",
    "memory_item_from_supply_chain_evidence",
]
