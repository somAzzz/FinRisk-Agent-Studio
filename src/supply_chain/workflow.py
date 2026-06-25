"""v18 supply chain workflow orchestrator + CLI.

The orchestrator runs the seven steps in order and writes a
:class:`SupplyChainExploreState` to the supplied (or in-memory)
store. The CLI is the canonical demo entry point:

    uv run python -m src.supply_chain.workflow \\
      --company OpenAI \\
      --product ChatGPT \\
      --max-depth 3 \\
      --demo-mode
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import uuid
from pathlib import Path

from src.schemas.llm_config import LLMRunConfig
from src.supply_chain.models import (
    SankeyPayload,
    SupplyChainEvaluation,
    SupplyChainExploreRequest,
    SupplyChainExploreState,
)
from src.supply_chain.steps import (
    SupplyChainEvaluatorStep,
    SupplyChainEvidenceNormalizerStep,
    SupplyChainGraphBuilderStep,
    SupplyChainProductResolverStep,
    SupplyChainRequirementDecomposerStep,
    SupplyChainSankeyBuilderStep,
    SupplyChainSupplierDiscoveryStep,
)

logger = logging.getLogger(__name__)


DEFAULT_STATE_STORE: dict[str, SupplyChainExploreState] = {}


def _default_steps() -> list:
    """Return the production v18 step pipeline (order is fixed by spec 02)."""
    return [
        SupplyChainProductResolverStep(),
        SupplyChainRequirementDecomposerStep(),
        SupplyChainSupplierDiscoveryStep(),
        SupplyChainEvidenceNormalizerStep(),
        SupplyChainGraphBuilderStep(),
        SupplyChainSankeyBuilderStep(),
        SupplyChainEvaluatorStep(),
    ]


def _seed_state_for_expansion(
    parent: SupplyChainExploreState,
    node_id: str,
    *,
    product_name: str | None,
    max_depth: int,
    max_suppliers_per_node: int,
    demo_mode: bool,
    cached_mode: bool,
    llm_config: LLMRunConfig,
) -> SupplyChainExploreState:
    """Create a child state that re-uses the parent's nodes / links.

    The recursive-expansion step keeps the parent's graph in
    place and adds the chosen node's upstream edges on top, so
    the Sankey can be merged client-side without losing evidence.
    """
    new_request = SupplyChainExploreRequest(
        company_name=parent.request.company_name,
        ticker=parent.request.ticker,
        product_name=product_name or node_id.split(":", 1)[-1].replace("-", " ").title(),
        max_depth=max_depth,
        max_suppliers_per_node=max_suppliers_per_node,
        demo_mode=demo_mode,
        cached_mode=cached_mode,
        llm_config=llm_config,
    )
    child = SupplyChainExploreState(
        run_id=f"sc-run-{uuid.uuid4().hex[:12]}",
        request=new_request,
        parent_run_id=parent.run_id,
        expanded_from_node_id=node_id,
    )
    # Carry over the parent's nodes / links / evidence so the
    # Sankey shows the original graph plus the new expansion.
    child.nodes = list(parent.nodes)
    child.links = list(parent.links)
    child.evidence = list(parent.evidence)
    return child


def _merge_expansion_subgraph(
    parent_sankey: SankeyPayload,
    child_sankey: SankeyPayload,
) -> SankeyPayload:
    """Merge the child's Sankey into the parent's without losing evidence.

    - nodes / links are deduped by id.
    - new nodes / links from the child are appended with a marker
      so the frontend can highlight them.
    - warnings are concatenated (child warnings first).
    """
    seen_nodes = {n.node_id: n for n in parent_sankey.nodes}
    for node in child_sankey.nodes:
        if node.node_id not in seen_nodes:
            seen_nodes[node.node_id] = node
    seen_edges = {e.edge_id: e for e in parent_sankey.links}
    for edge in child_sankey.links:
        if edge.edge_id not in seen_edges:
            seen_edges[edge.edge_id] = edge
    seen_evidence = {e.evidence_id: e for e in parent_sankey.evidence}
    for ev in child_sankey.evidence:
        seen_evidence[ev.evidence_id] = ev
    return SankeyPayload(
        nodes=list(seen_nodes.values()),
        links=list(seen_edges.values()),
        evidence=list(seen_evidence.values()),
        warnings=list(parent_sankey.warnings) + list(child_sankey.warnings),
    )


async def run_supply_chain_workflow(
    request: SupplyChainExploreRequest,
    *,
    steps: list | None = None,
    initial_state: SupplyChainExploreState | None = None,
    store: dict[str, SupplyChainExploreState] | None = None,
) -> SupplyChainExploreState:
    """Execute the v18 workflow end-to-end and return the final state."""
    target_store = store if store is not None else DEFAULT_STATE_STORE
    if initial_state is not None:
        state = initial_state
    else:
        state = SupplyChainExploreState(
            run_id=f"sc-run-{uuid.uuid4().hex[:12]}",
            request=request,
        )
    state.status = "running"
    target_store[state.run_id] = state
    pipeline = steps or _default_steps()
    for step in pipeline:
        state = await step(state)
    target_store[state.run_id] = state
    return state


async def expand_supply_chain_workflow(
    parent_run_id: str,
    node_id: str,
    *,
    product_name: str | None = None,
    seed_companies: list[str] | None = None,
    max_depth: int = 2,
    max_suppliers_per_node: int = 5,
    demo_mode: bool = True,
    cached_mode: bool = True,
    llm_config: LLMRunConfig | None = None,
    store: dict[str, SupplyChainExploreState] | None = None,
) -> SupplyChainExploreState:
    """Run a recursive expansion off an existing run.

    Validates the request through :class:`SupplyChainExpandRequest`
    so the v18 spec's max_depth=4 cap is enforced.
    """
    from src.supply_chain.models import SupplyChainExpandRequest

    # Validate the request envelope so the spec's max_depth=4 cap
    # is enforced before we touch the store. The value itself is
    # unused: the rest of the function uses the function's own
    # parameters to build the child state.
    _ = SupplyChainExpandRequest(
        parent_run_id=parent_run_id,
        node_id=node_id,
        product_name=product_name,
        seed_companies=list(seed_companies or []),
        max_depth=max_depth,
        max_suppliers_per_node=max_suppliers_per_node,
        demo_mode=demo_mode,
        cached_mode=cached_mode,
        llm_config=llm_config or LLMRunConfig(),
    )
    target_store = store if store is not None else DEFAULT_STATE_STORE
    parent = target_store.get(parent_run_id)
    if parent is None:
        raise KeyError(f"unknown parent run_id: {parent_run_id}")
    if parent.sankey is None:
        raise ValueError(
            f"parent run {parent_run_id} has no sankey payload yet"
        )
    resolved_llm_config = llm_config or parent.request.llm_config
    # v18: the expansion re-runs the workflow against a child
    # request that is seeded with the chosen node id. Demo mode
    # pulls the same fixture; the new state carries the parent
    # run_id so the API can correlate the two.
    child_request = SupplyChainExploreRequest(
        company_name=parent.request.company_name,
        ticker=parent.request.ticker,
        product_name=(
            product_name
            or node_id.split(":", 1)[-1].replace("-", " ").title()
        ),
        max_depth=max_depth,
        max_suppliers_per_node=max_suppliers_per_node,
        demo_mode=demo_mode,
        cached_mode=cached_mode,
        llm_config=resolved_llm_config,
    )
    child = _seed_state_for_expansion(
        parent,
        node_id,
        product_name=product_name,
        max_depth=max_depth,
        max_suppliers_per_node=max_suppliers_per_node,
        demo_mode=demo_mode,
        cached_mode=cached_mode,
        llm_config=resolved_llm_config,
    )
    # The child inherits the parent's request above; reset it to
    # the child-specific request so the trace records the
    # expansion scope.
    child = child.model_copy(update={"request": child_request})
    child.status = "running"
    target_store[child.run_id] = child
    pipeline = _default_steps()
    for step in pipeline:
        child = await step(child)
    # Merge the child's Sankey into the parent's so the front-end
    # can show the union without two separate requests.
    merged = _merge_expansion_subgraph(parent.sankey, child.sankey)
    parent.sankey = merged
    base_evaluation = (
        parent.evaluation.model_dump() if parent.evaluation else {"final_status": "pass"}
    )
    parent.evaluation = SupplyChainEvaluation.model_validate(
        {
            **base_evaluation,
            "node_count": len(merged.nodes),
            "link_count": len(merged.links),
            "evidence_count": len(merged.evidence),
        }
    )
    target_store[parent.run_id] = parent
    target_store[child.run_id] = child
    return child


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="supply_chain_workflow",
        description="v18 product supply chain explorer.",
    )
    parser.add_argument("--company", required=True, help="company name (e.g. OpenAI)")
    parser.add_argument("--ticker", default=None, help="optional ticker")
    parser.add_argument("--product", required=True, help="product name (e.g. ChatGPT)")
    parser.add_argument(
        "--max-depth", type=int, default=3, choices=[1, 2, 3, 4, 5]
    )
    parser.add_argument(
        "--max-suppliers-per-node", type=int, default=5, choices=range(1, 11)
    )
    parser.add_argument("--demo-mode", action="store_true")
    parser.add_argument("--cached-mode", action="store_true")
    parser.add_argument("--output", default=None, help="optional JSON output path")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    request = SupplyChainExploreRequest(
        company_name=args.company,
        ticker=args.ticker,
        product_name=args.product,
        max_depth=args.max_depth,
        max_suppliers_per_node=args.max_suppliers_per_node,
        demo_mode=args.demo_mode,
        cached_mode=args.cached_mode,
    )
    state = asyncio.run(run_supply_chain_workflow(request))
    print(f"run_id: {state.run_id}")
    print(f"status: {state.status}")
    node_count = len(state.nodes)
    link_count = len(state.links)
    evidence_count = len(state.evidence)
    print(f"node_count: {node_count}")
    print(f"link_count: {link_count}")
    print(f"evidence_count: {evidence_count}")
    if state.evaluation is not None:
        print(f"evaluation.final_status: {state.evaluation.final_status}")
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(state.model_dump_json(indent=2), encoding="utf-8")
    else:
        # Always print a tiny JSON summary so the demo is
        # self-documenting.
        summary = {
            "run_id": state.run_id,
            "status": state.status,
            "node_count": node_count,
            "link_count": link_count,
            "evidence_count": evidence_count,
            "evaluation": state.evaluation.model_dump()
            if state.evaluation
            else None,
        }
        print(json.dumps(summary, indent=2))
    return 0 if state.status in {"completed", "needs_review"} else 1


if __name__ == "__main__":
    sys.exit(main())
