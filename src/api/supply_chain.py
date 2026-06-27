"""v18 supply chain API routes.

Exposes four routes:

- ``POST /supply-chain/explore`` — start a new run.
- ``GET  /supply-chain/{run_id}`` — status / counts.
- ``GET  /supply-chain/{run_id}/sankey`` — full Sankey payload.
- ``POST /supply-chain/expand`` — recursive expansion.

The v18 routes live next to the v15/v17 routes in
``src.api.main``. The store is a plain ``dict`` (in-memory) so
the demo runs offline; production can swap in SQLite / Redis.
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from src.api.store_factory import get_supply_chain_store
from src.supply_chain.models import (
    SankeyPayload,
    SupplyChainEvaluation,
    SupplyChainExpandRequest,
    SupplyChainExploreRequest,
    SupplyChainExploreState,
)
from src.supply_chain.sankey import build_sankey_payload
from src.supply_chain.workflow import (
    expand_supply_chain_workflow,
    run_supply_chain_workflow,
)

logger = logging.getLogger(__name__)


def _background_enabled() -> bool:
    return os.environ.get("FINRISK_SKIP_BACKGROUND") != "1"


def _demo_enabled_for_tests() -> bool:
    """Allow fixture-only supply-chain runs only in explicit test mode."""
    return os.environ.get("FINRISK_ALLOW_SUPPLY_CHAIN_DEMO") == "1"


def _force_real_explore_request(
    request: SupplyChainExploreRequest,
) -> SupplyChainExploreRequest:
    if _demo_enabled_for_tests():
        return request
    if not (request.demo_mode or request.cached_mode):
        return request
    return request.model_copy(
        update={
            "demo_mode": False,
            "cached_mode": False,
        }
    )


def _force_real_expand_request(
    request: SupplyChainExpandRequest,
) -> SupplyChainExpandRequest:
    if _demo_enabled_for_tests():
        return request
    if not (request.demo_mode or request.cached_mode):
        return request
    return request.model_copy(
        update={
            "demo_mode": False,
            "cached_mode": False,
        }
    )


router = APIRouter(prefix="/supply-chain")
_background_tasks: set[asyncio.Task] = set()


# ---------------------------------------------------------------------------
# Request / response shapes
# ---------------------------------------------------------------------------


class SupplyChainExploreResponse(BaseModel):
    run_id: str
    status: str
    sankey_url: str | None = None
    error: str | None = None


class SupplyChainStatusResponse(BaseModel):
    run_id: str
    status: str
    request: SupplyChainExploreRequest
    current_step: str | None = None
    node_count: int
    link_count: int
    evidence_count: int
    parent_run_id: str | None = None
    expanded_from_node_id: str | None = None
    evaluation: SupplyChainEvaluation | None = None
    trace: list[dict]
    warnings: list[str]
    fallback_events: list[str]
    metrics: dict[str, int]


class SupplyChainSankeyResponse(BaseModel):
    run_id: str
    sankey: SankeyPayload | None = None


# ---------------------------------------------------------------------------
# Background runner
# ---------------------------------------------------------------------------


async def _run_and_store(request: SupplyChainExploreRequest) -> SupplyChainExploreState:
    """Run the workflow and store the result."""
    try:
        return await run_supply_chain_workflow(request)
    except Exception:
        logger.exception("supply chain workflow %s failed", request.product_name)
        raise


async def _run_existing_state(state: SupplyChainExploreState) -> None:
    """Background entry point that fills an already-created queued state."""
    try:
        await run_supply_chain_workflow(
            state.request,
            initial_state=state,
            store=get_supply_chain_store(),
        )
    except Exception as exc:
        logger.exception("supply chain workflow %s failed", state.run_id)
        state.status = "failed"
        state.warnings.append(f"{type(exc).__name__}: {exc}")
        await get_supply_chain_store().update(state)


async def _expand_existing_state(request: SupplyChainExpandRequest, run_id: str) -> None:
    """Background entry point for recursive expansion."""
    try:
        await expand_supply_chain_workflow(
            request.parent_run_id,
            request.node_id,
            product_name=request.product_name,
            seed_companies=request.seed_companies,
            max_depth=request.max_depth,
            max_suppliers_per_node=request.max_suppliers_per_node,
            demo_mode=request.demo_mode,
            cached_mode=request.cached_mode,
            llm_config=request.llm_config,
            store=get_supply_chain_store(),
            run_id=run_id,
        )
    except Exception as exc:
        logger.exception("supply chain expansion %s failed", run_id)
        child = await get_supply_chain_store().get(run_id)
        if child is not None:
            child.status = "failed"
            child.warnings.append(f"{type(exc).__name__}: {exc}")
            await get_supply_chain_store().update(child)


def _schedule(coro) -> None:
    """Schedule ``coro`` and retain the task until completion."""
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post(
    "/explore",
    response_model=SupplyChainExploreResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_supply_chain_explore(
    request: SupplyChainExploreRequest,
) -> SupplyChainExploreResponse:
    """Start a new v18 supply chain run."""
    request = _force_real_explore_request(request)
    state = SupplyChainExploreState(
        run_id=f"sc-run-{uuid.uuid4().hex[:12]}",
        request=request,
        status="queued",
    )
    await get_supply_chain_store().update(state)
    if _background_enabled():
        _schedule(_run_existing_state(state))
    else:
        state = await run_supply_chain_workflow(
            request,
            initial_state=state,
            store=get_supply_chain_store(),
        )
    return SupplyChainExploreResponse(
        run_id=state.run_id,
        status=state.status,
        sankey_url=f"/supply-chain/{state.run_id}/sankey",
    )


@router.post(
    "/expand",
    response_model=SupplyChainExploreResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def expand_supply_chain(
    request: SupplyChainExpandRequest,
) -> SupplyChainExploreResponse:
    """Recursively expand from an existing run's node."""
    request = _force_real_expand_request(request)
    parent = await get_supply_chain_store().get(request.parent_run_id)
    if parent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"unknown parent run_id: {request.parent_run_id}",
        )
    if parent.sankey is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"parent run {request.parent_run_id} has no sankey payload yet",
        )
    child_request = SupplyChainExploreRequest(
        company_name=parent.request.company_name,
        ticker=parent.request.ticker,
        product_name=(
            request.product_name
            or request.node_id.split(":", 1)[-1].replace("-", " ").title()
        ),
        max_depth=request.max_depth,
        max_suppliers_per_node=request.max_suppliers_per_node,
        demo_mode=request.demo_mode,
        cached_mode=request.cached_mode,
        llm_config=request.llm_config or parent.request.llm_config,
    )
    child = SupplyChainExploreState(
        run_id=f"sc-run-{uuid.uuid4().hex[:12]}",
        request=child_request,
        status="queued",
        parent_run_id=parent.run_id,
        expanded_from_node_id=request.node_id,
    )
    await get_supply_chain_store().update(child)
    if _background_enabled():
        _schedule(_expand_existing_state(request, child.run_id))
        return SupplyChainExploreResponse(
            run_id=child.run_id,
            status=child.status,
            sankey_url=f"/supply-chain/{parent.run_id}/sankey",
        )
    try:
        child = await expand_supply_chain_workflow(
            request.parent_run_id,
            request.node_id,
            product_name=request.product_name,
            seed_companies=request.seed_companies,
            max_depth=request.max_depth,
            max_suppliers_per_node=request.max_suppliers_per_node,
            demo_mode=request.demo_mode,
            cached_mode=request.cached_mode,
            llm_config=request.llm_config,
            store=get_supply_chain_store(),
            run_id=child.run_id,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"unknown parent run_id: {request.parent_run_id}",
        ) from exc
    return SupplyChainExploreResponse(
        run_id=child.run_id,
        status=child.status,
        sankey_url=f"/supply-chain/{parent.run_id}/sankey",
    )


@router.get(
    "/health",
    response_model=dict,
)
async def supply_chain_health() -> dict:
    return {"status": "ok", "runs": await get_supply_chain_store().size()}


@router.get(
    "",
    response_model=list[SupplyChainExploreResponse],
)
async def list_supply_chain_runs(limit: int = 20) -> list[SupplyChainExploreResponse]:
    """Return recent supply-chain runs."""
    states = await get_supply_chain_store().list_recent(limit)
    return [
        SupplyChainExploreResponse(
            run_id=state.run_id,
            status=state.status,
            sankey_url=f"/supply-chain/{state.run_id}/sankey",
        )
        for state in states
    ]


@router.get(
    "/{run_id}",
    response_model=SupplyChainStatusResponse,
)
async def get_supply_chain_status(run_id: str) -> SupplyChainStatusResponse:
    state = await get_supply_chain_store().get(run_id)
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="unknown supply-chain run",
        )
    node_count = len(state.sankey.nodes) if state.sankey is not None else len(state.nodes)
    link_count = len(state.sankey.links) if state.sankey is not None else len(state.links)
    evidence_count = (
        len(state.sankey.evidence) if state.sankey is not None else len(state.evidence)
    )
    current_step = None
    for event in reversed(state.trace):
        if event.status == "running":
            current_step = event.step_name
            break
    return SupplyChainStatusResponse(
        run_id=state.run_id,
        status=state.status,
        request=state.request,
        current_step=current_step,
        node_count=node_count,
        link_count=link_count,
        evidence_count=evidence_count,
        parent_run_id=state.parent_run_id,
        expanded_from_node_id=state.expanded_from_node_id,
        evaluation=state.evaluation,
        trace=[e.model_dump(mode="json") for e in state.trace],
        warnings=list(state.warnings),
        fallback_events=list(state.fallback_events),
        metrics=dict(state.metrics),
    )


@router.get(
    "/{run_id}/sankey",
    response_model=SupplyChainSankeyResponse,
)
async def get_supply_chain_sankey(run_id: str) -> SupplyChainSankeyResponse:
    state = await get_supply_chain_store().get(run_id)
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="unknown supply-chain run",
        )
    sankey = state.sankey
    if sankey is not None:
        repaired_state = state.model_copy(
            update={
                "nodes": list(sankey.nodes),
                "links": list(sankey.links),
                "evidence": list(sankey.evidence),
                "warnings": list(sankey.warnings),
            }
        )
        repaired = build_sankey_payload(repaired_state)
        if repaired != sankey:
            state.sankey = repaired
            await get_supply_chain_store().update(state)
            sankey = repaired
    return SupplyChainSankeyResponse(run_id=state.run_id, sankey=sankey)


__all__ = [
    "SupplyChainExploreResponse",
    "SupplyChainSankeyResponse",
    "SupplyChainStatusResponse",
    "_run_and_store",
    "list_supply_chain_runs",
    "router",
]
