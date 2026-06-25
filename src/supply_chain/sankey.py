"""v18 Sankey payload builder.

The builder consumes ``SupplyChainExploreState`` and produces a
:class:`SankeyPayload` (Pydantic model). Cycle detection is
delegated to the model validator so any cycle the builder emits
will fail at validation time.
"""

from __future__ import annotations

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
    # 1. node dedup
    seen_nodes: dict[str, SupplyChainNode] = {}
    for node in state.nodes:
        if node.node_id in seen_nodes:
            continue
        seen_nodes[node.node_id] = node

    # 2. edge dedup + self-loop + hypothesised cycle removal
    adjacency: dict[str, list[str]] = {nid: [] for nid in seen_nodes}
    seen_edges: dict[str, SupplyChainEdge] = {}
    for edge in state.links:
        if edge.source_node_id not in seen_nodes or edge.target_node_id not in seen_nodes:
            state.warnings.append(
                f"edge {edge.edge_id} references unknown node; skipped"
            )
            continue
        if edge.source_node_id == edge.target_node_id:
            state.warnings.append(
                f"edge {edge.edge_id} is a self-loop; skipped"
            )
            continue
        if edge.edge_id in seen_edges:
            continue
        seen_edges[edge.edge_id] = edge
        if edge.relation_type != "hypothesized":
            adjacency[edge.source_node_id].append(edge.target_node_id)

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
    if unsupported:
        final_status = "fail"
    elif hypothesised or low_confidence or diversity < 0.34:
        final_status = "needs_review"
    elif not sankey.nodes:
        final_status = "fail"
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
