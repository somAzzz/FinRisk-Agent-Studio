"""v18 Sankey payload builder.

The builder consumes ``SupplyChainExploreState`` and produces a
:class:`SankeyPayload` (Pydantic model). Cycle detection is
delegated to the model validator so any cycle the builder emits
will fail at validation time.
"""

from __future__ import annotations

import re

from src.supply_chain.models import (
    SankeyPayload,
    SupplyChainEdge,
    SupplyChainEvaluation,
    SupplyChainExploreState,
    SupplyChainNode,
)


def build_sankey_payload(state: SupplyChainExploreState) -> SankeyPayload:
    """Convert ``state`` into a :class:`SankeyPayload`.

    The builder performs three transforms before the model
    validator runs:

    1. drop self-loops (defensive; the validator would also catch
       them);
    2. drop hypothesised cycles (Pydantic's validator only fails
       on *confirmed* cycles; hypothesised edges are removed and
       a warning is recorded);
    3. merge node / edge duplicates by ``node_id`` / ``edge_id``.

    The builder never raises; the underlying validator surfaces
    structural problems and the v18 evaluator decides the final
    workflow status.
    """
    # 1. node dedup + canonical synonym merge
    seen_nodes, node_aliases = _canonicalise_nodes(state.nodes)
    seen_nodes = _repair_expansion_product_roots(state, seen_nodes)

    # 2. edge dedup + self-loop + hypothesised cycle removal
    adjacency: dict[str, list[str]] = {nid: [] for nid in seen_nodes}
    seen_edges: dict[str, SupplyChainEdge] = {}
    for edge in state.links:
        source_id = _canonical_node_ref(edge.source_node_id, node_aliases)
        target_id = _canonical_node_ref(edge.target_node_id, node_aliases)
        if source_id not in seen_nodes or target_id not in seen_nodes:
            state.warnings.append(
                f"edge {edge.edge_id} references unknown node; skipped"
            )
            continue
        if source_id == target_id:
            state.warnings.append(
                f"edge {edge.edge_id} is a self-loop; skipped"
            )
            continue
        rewritten = edge.model_copy(
            update={
                "edge_id": _canonical_edge_id(edge.edge_id, source_id, target_id),
                "source_node_id": source_id,
                "target_node_id": target_id,
            }
        )
        if rewritten.edge_id in seen_edges:
            continue
        seen_edges[rewritten.edge_id] = rewritten
        if rewritten.relation_type != "hypothesized":
            adjacency[rewritten.source_node_id].append(rewritten.target_node_id)

    # 3. hypothesised cycle removal: BFS from each node to find
    # descendants; any hypothesised edge that re-introduces a node
    # already reachable is dropped.
    kept_edges: list[SupplyChainEdge] = []
    for edge in seen_edges.values():
        if edge.relation_type != "hypothesized":
            kept_edges.append(edge)
            continue
        if _creates_hypothesised_cycle(edge, adjacency):
            state.warnings.append(
                f"edge {edge.edge_id} creates a hypothesised cycle; dropped"
            )
            continue
        kept_edges.append(edge)
        adjacency[edge.source_node_id].append(edge.target_node_id)

    return SankeyPayload(
        nodes=list(seen_nodes.values()),
        links=kept_edges,
        evidence=list(state.evidence),
        warnings=list(state.warnings),
    )


def _canonicalise_nodes(
    nodes: list[SupplyChainNode],
) -> tuple[dict[str, SupplyChainNode], dict[str, str]]:
    by_key: dict[tuple[str, str], SupplyChainNode] = {}
    aliases: dict[str, str] = {}
    for node in nodes:
        key = (node.node_type, _canonical_label_key(node.label))
        existing = by_key.get(key)
        if existing is None:
            canonical = _canonical_node(node)
            by_key[key] = canonical
            aliases[node.node_id] = canonical.node_id
            continue
        aliases[node.node_id] = existing.node_id
        by_key[key] = _merge_node(existing, node)
        state_id = by_key[key].node_id
        for source_id, target_id in list(aliases.items()):
            if target_id == existing.node_id:
                aliases[source_id] = state_id
    canonical_nodes: dict[str, SupplyChainNode] = {}
    for original_node in by_key.values():
        parent_node_id = (
            _canonical_node_ref(original_node.parent_node_id, aliases)
            if original_node.parent_node_id
            else None
        )
        node = (
            original_node.model_copy(update={"parent_node_id": parent_node_id})
            if parent_node_id != original_node.parent_node_id
            else original_node
        )
        canonical_nodes[node.node_id] = node
    return canonical_nodes, aliases


def _canonical_node_ref(node_id: str, aliases: dict[str, str]) -> str:
    if node_id in aliases:
        return aliases[node_id]
    if ":" not in node_id:
        return node_id
    node_type, raw_label = node_id.split(":", 1)
    return f"{node_type}:{_slug(raw_label.replace('-', ' '))}"


def _repair_expansion_product_roots(
    state: SupplyChainExploreState,
    nodes: dict[str, SupplyChainNode],
) -> dict[str, SupplyChainNode]:
    """Attach legacy expansion product roots to their matching anchor node.

    Older merged Sankey payloads introduced expansion seeds such as
    ``product:nvidia`` as additional roots under the seed company. When
    a same-name non-product node exists, the product is the expansion
    subgraph root and should sit below that anchor.
    """
    anchors: dict[str, SupplyChainNode] = {}
    for node in nodes.values():
        if node.node_type == "product":
            continue
        anchors.setdefault(_canonical_label_key(node.label), node)
        if ":" in node.node_id:
            anchors.setdefault(
                _canonical_label_key(node.node_id.split(":", 1)[1].replace("-", " ")),
                node,
            )
    repaired: dict[str, SupplyChainNode] = {}
    for original_node in nodes.values():
        node_key = _canonical_label_key(original_node.label)
        anchor = anchors.get(node_key)
        if (
            original_node.node_type == "product"
            and anchor is not None
            and original_node.parent_node_id != anchor.node_id
        ):
            node = original_node.model_copy(
                update={
                    "parent_node_id": anchor.node_id,
                    "depth": min(anchor.depth + 1, 10),
                    "metadata": {
                        **original_node.metadata,
                        "legacy_expansion_root_repaired": True,
                    },
                }
            )
        else:
            node = original_node
        repaired[node.node_id] = node
    return repaired


def _canonical_node(node: SupplyChainNode) -> SupplyChainNode:
    label = _canonical_display_label(node.label)
    node_id = f"{node.node_type}:{_slug(label)}"
    metadata = {
        **node.metadata,
        "canonical_label": label,
    }
    return node.model_copy(
        update={
            "node_id": node_id,
            "label": label,
            "normalized_name": _canonical_label_key(label),
            "metadata": metadata,
        }
    )


def _merge_node(left: SupplyChainNode, right: SupplyChainNode) -> SupplyChainNode:
    right = _canonical_node(right)
    evidence_ids = sorted({*left.evidence_ids, *right.evidence_ids})
    aliases = sorted(
        {
            str(value)
            for value in (
                left.metadata.get("aliases", []),
                right.metadata.get("aliases", []),
                left.label,
                right.label,
            )
            if isinstance(value, str) and value.strip()
        }
    )
    metadata = {
        **left.metadata,
        **right.metadata,
        "aliases": aliases,
        "merged_duplicate_count": int(left.metadata.get("merged_duplicate_count", 1))
        + 1,
    }
    preferred = left if left.confidence >= right.confidence else right
    return preferred.model_copy(
        update={
            "node_id": left.node_id,
            "label": left.label,
            "normalized_name": left.normalized_name,
            "confidence": max(left.confidence, right.confidence),
            "evidence_ids": evidence_ids,
            "metadata": metadata,
        }
    )


def _canonical_display_label(value: str) -> str:
    key = _canonical_label_key(value)
    known = {
        "rare earth element": "Rare earth elements",
        "rare earth metal": "Rare earth elements",
        "ree": "Rare earth elements",
    }
    if key in known:
        return known[key]
    return " ".join(value.strip().split())


def _canonical_label_key(value: str) -> str:
    text = value.strip().lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\b(?:and|the|for|supply|supplies|supplier|suppliers)\b", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    synonym_map = {
        "rare earth elements": "rare earth element",
        "rare earth element": "rare earth element",
        "rare earth metals": "rare earth element",
        "rare earth metal": "rare earth element",
        "rees": "rare earth element",
        "ree": "rare earth element",
    }
    return synonym_map.get(text, _singularise_key(text))


def _singularise_key(value: str) -> str:
    words = value.split()
    if not words:
        return value
    last = words[-1]
    if len(last) > 3 and last.endswith("ies"):
        words[-1] = f"{last[:-3]}y"
    elif len(last) > 3 and last.endswith("s") and not last.endswith("ss"):
        words[-1] = last[:-1]
    return " ".join(words)


def _slug(value: str) -> str:
    return "-".join(_canonical_label_key(value).split())


def _canonical_edge_id(edge_id: str, source_id: str, target_id: str) -> str:
    suffix = edge_id.rsplit(":", 1)[-1] if ":" in edge_id else "edge"
    return f"sc-edge:{source_id}:{target_id}:{suffix}"


def _creates_hypothesised_cycle(
    edge: SupplyChainEdge,
    adjacency: dict[str, list[str]],
) -> bool:
    """Return True if adding ``edge`` would close a cycle in ``adjacency``."""
    target = edge.target_node_id
    visited: set[str] = {target}
    stack: list[str] = [target]
    while stack:
        node = stack.pop()
        if node == edge.source_node_id:
            return True
        for nxt in adjacency[node]:
            if nxt in visited:
                continue
            visited.add(nxt)
            stack.append(nxt)
    return False


def evaluate_state(
    state: SupplyChainExploreState,
    sankey: SankeyPayload,
) -> SupplyChainEvaluation:
    """Compute the v18 :class:`SupplyChainEvaluation` for a finished state."""
    confirmed = sum(1 for e in sankey.links if e.relation_type != "hypothesized")
    hypothesised = sum(1 for e in sankey.links if e.relation_type == "hypothesized")
    unsupported = [
        e.edge_id
        for e in sankey.links
        if e.relation_type != "hypothesized" and not e.evidence_ids
    ]
    low_confidence = [
        e.edge_id
        for e in sankey.links
        if e.confidence < 0.5
    ]
    sources = {ev.source_type for ev in sankey.evidence}
    diversity = min(1.0, len(sources) / 3.0) if sources else 0.0
    final_status: str
    if unsupported or not sankey.nodes:
        final_status = "fail"
    elif (
        not sankey.links
        or sankey.warnings
        or hypothesised
        or low_confidence
        or diversity < 0.34
    ):
        final_status = "needs_review"
    else:
        final_status = "pass"
    return SupplyChainEvaluation(
        final_status=final_status,  # type: ignore[arg-type]
        schema_valid=True,
        graph_connected=bool(sankey.nodes) and _is_connected(sankey),
        acyclic_for_sankey=True,
        confirmed_edges_have_evidence=not unsupported,
        node_count=len(sankey.nodes),
        link_count=len(sankey.links),
        evidence_count=len(sankey.evidence),
        confirmed_edge_count=confirmed,
        hypothesised_edge_count=hypothesised,
        unsupported_edges=unsupported,
        low_confidence_edges=low_confidence,
        source_diversity_score=diversity,
        warnings=list(sankey.warnings),
        human_review_required=final_status != "pass",
    )


def _is_connected(sankey: SankeyPayload) -> bool:
    """Return True if every non-root node is touched by at least one edge."""
    if not sankey.nodes:
        return False
    touched: set[str] = set()
    for edge in sankey.links:
        touched.add(edge.source_node_id)
        touched.add(edge.target_node_id)
    root_ids = {n.node_id for n in sankey.nodes if n.depth == 0}
    return all(n.node_id in touched or n.node_id in root_ids for n in sankey.nodes)


__all__ = ["build_sankey_payload", "evaluate_state"]
