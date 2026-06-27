"""v18 Step 3: supplier discovery."""

from __future__ import annotations

import json
import time
from typing import Any

from src.schemas.tool_trace import ToolLoopTrace
from src.supply_chain.evidence import build_evidence_from_search
from src.supply_chain.llm import (
    build_supply_chain_llm_client,
    complete_json_with_trace,
)
from src.supply_chain.models import (
    NormalizedSupplyChainEvidence,
    ProviderCall,
    SupplierCandidate,
    SupplyChainEdge,
    SupplyChainExploreState,
    SupplyChainNode,
)
from src.supply_chain.steps._base import SupplyChainStep

KNOWN_SUPPLIERS: dict[str, tuple[str, str | None]] = {
    "microsoft": ("Microsoft", "MSFT"),
    "azure": ("Microsoft", "MSFT"),
    "oracle": ("Oracle", "ORCL"),
    "coreweave": ("CoreWeave", None),
    "nvidia": ("NVIDIA", "NVDA"),
    "amd": ("AMD", "AMD"),
    "intel": ("Intel", "INTC"),
    "sk hynix": ("SK hynix", None),
    "samsung": ("Samsung", None),
    "micron": ("Micron", "MU"),
    "broadcom": ("Broadcom", "AVGO"),
    "arista": ("Arista Networks", "ANET"),
    "cisco": ("Cisco", "CSCO"),
    "marvell": ("Marvell", "MRVL"),
    "tsmc": ("TSMC", "TSM"),
    "asml": ("ASML", "ASML"),
    "synopsys": ("Synopsys", "SNPS"),
    "cadence": ("Cadence", "CDNS"),
}


def _slug(value: str) -> str:
    return value.strip().lower().replace(" ", "-")


def _supplier_from_text(text: str) -> tuple[str, str | None] | None:
    lowered = text.lower()
    for needle, supplier in KNOWN_SUPPLIERS.items():
        if needle in lowered:
            return supplier
    return None


def _intent_for_requirement(label: str) -> str:
    lowered = label.lower()
    if "cloud" in lowered:
        return "cloud_dependency"
    if "power" in lowered or "energy" in lowered:
        return "datacenter_power"
    if any(token in lowered for token in ("gpu", "cpu", "hbm", "semiconductor")):
        return "semiconductor_supply_chain"
    return "component_supplier"


class SupplyChainSupplierDiscoveryStep(SupplyChainStep):
    """Attach supplier edges to each requirement node.

    In demo mode the step is a no-op: the supplier edges are
    already part of the fixture consumed by the requirement
    decomposer. In real mode, the step uses SearchRouter with
    deterministic extraction rules. This keeps the production path
    evidence-backed while avoiding LLM-only assertions.
    """

    name = "supplier_discovery"

    def __init__(
        self,
        *,
        search_router: Any | None = None,
        llm_client_factory: Any | None = None,
        llm_runtime_factory: Any | None = None,
        llm_shadow_mode: bool = False,
        max_results: int = 3,
    ) -> None:
        super().__init__()
        self._search_router = search_router
        self._llm_client_factory = llm_client_factory
        self._llm_runtime_factory = llm_runtime_factory
        self._llm_shadow_mode = llm_shadow_mode
        self._max_results = max_results

    async def run(
        self, state: SupplyChainExploreState
    ) -> SupplyChainExploreState:
        if state.request.demo_mode or state.request.cached_mode:
            return state
        requirement_nodes = [
            node for node in state.nodes
            if node.node_type in {"component", "service", "energy", "infrastructure"}
        ]
        _increment_metric(state, "requirement_count", len(requirement_nodes))
        self._add_llm_supplier_candidates(state, requirement_nodes)
        router = self._search_router
        if router is None:
            try:
                from src.tools.search_router import SearchRouter

                router = SearchRouter()
            except Exception as exc:
                state.fallback_events.append(
                    f"supplier_discovery:search router unavailable: {exc}"
                )
                return state
        for requirement in requirement_nodes[: state.request.max_suppliers_per_node * 2]:
            intent = _intent_for_requirement(requirement.label)
            query = (
                f"{state.request.company_name or state.request.ticker} "
                f"{state.request.product_name} {requirement.label}"
            )
            _increment_metric(state, "query_count")
            try:
                started = time.perf_counter()
                response = router.search(
                    query=query,
                    intent=intent,
                    max_results=self._max_results,
                )
                self._record_provider_call(
                    state,
                    ProviderCall(
                        provider=getattr(response, "provider", "search"),
                        operation="search",
                        status="success",
                        latency_ms=int((time.perf_counter() - started) * 1000),
                    ),
                )
            except Exception as exc:
                self._record_provider_call(
                    state,
                    ProviderCall(
                        provider=router.__class__.__name__,
                        operation="search",
                        status="failed",
                        latency_ms=0,
                        error=str(exc),
                    ),
                )
                state.fallback_events.append(
                    f"supplier_discovery:search failed for {requirement.node_id}: {exc}"
                )
                continue
            if not response.results:
                _increment_metric(state, "zero_result_query_count")
                state.warnings.append(
                    f"supplier_discovery:no search results for {requirement.label}"
                )
                continue
            _increment_metric(state, "raw_result_count", len(response.results))
            self._add_supplier_edges(state, requirement, response)
        if state.metrics.get("raw_result_count", 0) == 0:
            state.fallback_events.append("supplier_discovery:ZERO_SEARCH_RESULTS")
        elif state.metrics.get("evidence_row_count", 0) == 0:
            state.fallback_events.append("supplier_discovery:ZERO_EVIDENCE_ROWS")
        if not any(edge.relation_type == "supplied_by" for edge in state.links):
            state.fallback_events.append(
                "supplier_discovery:no confirmed suppliers discovered from search"
            )
        if self._llm_shadow_mode:
            self._run_llm_shadow(state, requirement_nodes)
        return state

    def _add_llm_supplier_candidates(
        self,
        state: SupplyChainExploreState,
        requirement_nodes: list[SupplyChainNode],
    ) -> None:
        if not requirement_nodes:
            return
        provider = state.request.llm_config.provider
        client = self._build_llm_client(state)
        if client is None:
            self._record_provider_call(
                state,
                ProviderCall(
                    provider=provider,
                    operation="propose_suppliers",
                    status="failed",
                    latency_ms=0,
                    error="LLM client unavailable",
                ),
            )
            state.fallback_events.append(
                "supplier_discovery:llm unavailable; used search-only discovery"
            )
            return
        payload, call = complete_json_with_trace(
            client=client,
            provider=provider,
            operation="propose_suppliers",
            system=(
                "You are a supply-chain analyst. Return compact JSON only. "
                "Treat suppliers as hypotheses unless source-backed evidence exists."
            ),
            prompt=_supplier_prompt(state, requirement_nodes),
            max_tokens=3200,
            temperature=0.1,
            retries=1,
        )
        self._record_provider_call(state, call)
        rows = _coerce_supplier_rows(payload)
        if not rows:
            state.fallback_events.append(
                "supplier_discovery:llm returned no supplier candidates"
            )
            return
        requirement_by_label = {
            node.label.strip().lower(): node for node in requirement_nodes
        }
        requirement_by_id = {node.node_id: node for node in requirement_nodes}
        existing_nodes = {node.node_id for node in state.nodes}
        existing_edges = {edge.edge_id for edge in state.links}
        added_edges = 0
        for row in rows[: state.request.max_suppliers_per_node * len(requirement_nodes)]:
            requirement = (
                requirement_by_id.get(row["requirement_node_id"])
                or requirement_by_label.get(row["requirement_label"].lower())
            )
            if requirement is None:
                continue
            supplier_name = row["supplier_name"]
            supplier_id = f"company:{_slug(supplier_name)}"
            if _is_seed_company(state, supplier_name, supplier_id):
                _increment_metric(state, "self_supplier_candidate_count")
                continue
            if supplier_id not in existing_nodes:
                state.nodes.append(
                    SupplyChainNode(
                        node_id=supplier_id,
                        node_type="company",
                        label=supplier_name,
                        normalized_name=_slug(supplier_name),
                        ticker=row["ticker"],
                        depth=requirement.depth + 1,
                        parent_node_id=requirement.node_id,
                        confidence=row["confidence"],
                        evidence_ids=[],
                        metadata={
                            "method": "llm_supplier_discovery",
                            "provider": provider,
                        },
                    )
                )
                existing_nodes.add(supplier_id)
            candidate = SupplierCandidate(
                supplier_name=supplier_name,
                ticker=row["ticker"],
                relation_type="hypothesized",
                product_or_service=row["product_or_service"] or requirement.label,
                evidence_ids=[],
                confidence=row["confidence"],
                uncertainty=row["uncertainty"]
                or "LLM hypothesis pending evidence confirmation",
                source_requirement_node_id=requirement.node_id,
            )
            _append_unique_candidates(state, [candidate])
            edge_id = f"sc-edge:{requirement.node_id}:{supplier_id}:supplied_by"
            if edge_id in existing_edges:
                continue
            state.links.append(
                SupplyChainEdge(
                    edge_id=edge_id,
                    source_node_id=requirement.node_id,
                    target_node_id=supplier_id,
                    relation_type="hypothesized",
                    value=0.45,
                    confidence=row["confidence"],
                    evidence_ids=[],
                    metadata={
                        "method": "llm_supplier_discovery",
                        "provider": provider,
                        "reason": row["uncertainty"]
                        or "LLM-proposed supplier candidate pending evidence",
                    },
                )
            )
            existing_edges.add(edge_id)
            added_edges += 1
            _increment_metric(state, "llm_supplier_edge_count")
        if added_edges:
            _increment_metric(state, "llm_supplier_candidate_count", added_edges)

    def _run_llm_shadow(
        self,
        state: SupplyChainExploreState,
        requirement_nodes: list[SupplyChainNode],
    ) -> None:
        runtime = self._default_llm_runtime()
        if runtime is None:
            state.fallback_events.append(
                "supplier_discovery:llm shadow unavailable; deterministic path used"
            )
            return
        for requirement in requirement_nodes[: state.request.max_suppliers_per_node * 2]:
            try:
                result = runtime.run(_llm_supplier_goal(state, requirement))
            except Exception as exc:
                state.fallback_events.append(
                    "supplier_discovery:llm shadow failed "
                    f"for {requirement.node_id}: {exc}"
                )
                continue
            state.llm_tool_traces.append(
                ToolLoopTrace(
                    mode=result.mode,
                    tool_events=result.tool_events,
                    budget_usage=result.budget_usage,
                )
            )
            candidates, evidence = _supplier_candidates_from_tool_events(
                requirement=requirement,
                result=result,
            )
            _append_unique_evidence(state, evidence)
            _append_unique_candidates(state, candidates)

    def _add_supplier_edges(
        self,
        state: SupplyChainExploreState,
        requirement: SupplyChainNode,
        response: Any,
    ) -> None:
        existing_nodes = {node.node_id for node in state.nodes}
        existing_edges = {edge.edge_id: edge for edge in state.links}
        existing_evidence = {ev.evidence_id for ev in state.evidence}
        llm_candidate_supplier_ids = {
            f"company:{_slug(candidate.supplier_name)}"
            for candidate in state.llm_supplier_candidates
            if candidate.source_requirement_node_id == requirement.node_id
        }
        added = 0
        for result in response.results:
            text = f"{result.title} {result.snippet} {result.url}"
            supplier = _supplier_from_text(text)
            if supplier is None:
                continue
            _increment_metric(state, "candidate_count")
            supplier_name, ticker = supplier
            supplier_id = f"company:{_slug(supplier_name)}"
            if _is_seed_company(state, supplier_name, supplier_id):
                _increment_metric(state, "self_supplier_candidate_count")
                continue
            if llm_candidate_supplier_ids and supplier_id not in llm_candidate_supplier_ids:
                _increment_metric(state, "search_supplier_not_in_llm_candidates")
                continue
            evidence_dict = build_evidence_from_search(
                {
                    "url": result.url,
                    "title": result.title,
                    "snippet": result.snippet,
                },
                query=response.query,
            )
            is_confirmed = bool(evidence_dict.pop("is_confirmed", False))
            evidence = NormalizedSupplyChainEvidence.model_validate(evidence_dict)
            if evidence.evidence_id not in existing_evidence:
                state.evidence.append(evidence)
                existing_evidence.add(evidence.evidence_id)
                _increment_metric(state, "evidence_row_count")
            if supplier_id not in existing_nodes:
                state.nodes.append(
                    SupplyChainNode(
                        node_id=supplier_id,
                        node_type="company",
                        label=supplier_name,
                        normalized_name=_slug(supplier_name),
                        ticker=ticker,
                        depth=requirement.depth + 1,
                        parent_node_id=requirement.node_id,
                        confidence=evidence.confidence,
                        evidence_ids=[evidence.evidence_id],
                        metadata={"method": "search_supplier_discovery"},
                    )
                )
                existing_nodes.add(supplier_id)
            relation_type = "supplied_by" if is_confirmed else "hypothesized"
            edge_id = f"sc-edge:{requirement.node_id}:{supplier_id}:supplied_by"
            if edge_id in existing_edges:
                if is_confirmed:
                    _upgrade_existing_edge_with_evidence(
                        state,
                        edge_id=edge_id,
                        evidence_id=evidence.evidence_id,
                        confidence=evidence.confidence,
                        provider=response.provider,
                        query=response.query,
                    )
                    _increment_metric(state, "supplier_edge_confirmed_count")
                continue
            state.links.append(
                SupplyChainEdge(
                    edge_id=edge_id,
                    source_node_id=requirement.node_id,
                    target_node_id=supplier_id,
                    relation_type=relation_type,
                    value=0.6,
                    confidence=evidence.confidence,
                    evidence_ids=[evidence.evidence_id] if is_confirmed else [],
                    metadata={
                        "query": response.query,
                        "provider": response.provider,
                        "method": "search_supplier_discovery",
                        **({} if is_confirmed else {"reason": "search result lacked URL or quote"}),
                    },
                )
            )
            existing_edges[edge_id] = state.links[-1]
            added += 1
            _increment_metric(state, "supplier_edge_count")
            if added >= state.request.max_suppliers_per_node:
                break

    @staticmethod
    def _record_provider_call(
        state: SupplyChainExploreState,
        call: ProviderCall,
    ) -> None:
        if not state.trace:
            return
        state.trace[-1].provider_calls.append(call)

    def _default_llm_runtime(self) -> Any | None:
        if self._llm_runtime_factory is not None:
            try:
                return self._llm_runtime_factory()
            except Exception:
                return None
        try:
            from src.agents.llm_runtime import LLMToolAgentRuntime
            from src.llm.deepseek_client import build_client_from_settings
            from src.tools.catalog import build_project_tool_catalog

            return LLMToolAgentRuntime(
                llm_client=build_client_from_settings(),
                tool_catalog=build_project_tool_catalog(scope="supply_chain"),
            )
        except Exception:
            return None

    def _build_llm_client(self, state: SupplyChainExploreState) -> Any | None:
        if self._llm_client_factory is not None:
            return self._llm_client_factory(state.request.llm_config)
        return build_supply_chain_llm_client(state.request.llm_config)


def _llm_supplier_goal(
    state: SupplyChainExploreState,
    requirement: SupplyChainNode,
) -> str:
    company = state.request.company_name or state.request.ticker or "the company"
    return (
        "Discover evidence-backed supplier or infrastructure dependency candidates. "
        "Use read-only tools only. Do not write graph edges. Return uncertainty. "
        f"Company: {company}. Product: {state.request.product_name}. "
        f"Requirement: {requirement.label}."
    )


def _supplier_prompt(
    state: SupplyChainExploreState,
    requirement_nodes: list[SupplyChainNode],
) -> str:
    company = state.request.company_name or state.request.ticker or "the company"
    requirements = [
        {"node_id": node.node_id, "label": node.label}
        for node in requirement_nodes[: state.request.max_suppliers_per_node * 2]
    ]
    return (
        "Propose likely upstream suppliers, infrastructure providers, or critical "
        "dependency companies for each requirement. Prefer named public companies "
        "when known, but include private companies if material.\n"
        f"Company: {company}\n"
        f"Product: {state.request.product_name}\n"
        f"Requirements: {json.dumps(requirements, ensure_ascii=False)}\n"
        "Return JSON with this exact shape:\n"
        '{"suppliers":[{"requirement_node_id":"component:gpu-accelerator",'
        '"requirement_label":"GPU accelerator","supplier_name":"NVIDIA",'
        '"ticker":"NVDA","product_or_service":"AI GPUs","confidence":0.7,'
        '"uncertainty":"why this is still a hypothesis"}]}\n'
        "Return minified JSON. Keep uncertainty under 12 words. "
        "Return at most two suppliers per requirement. Do not list the seed "
        "company itself as its own upstream supplier."
    )


def _coerce_supplier_rows(payload: Any) -> list[dict[str, Any]]:
    rows = None
    if isinstance(payload, dict):
        for key in (
            "suppliers",
            "supplier_candidates",
            "candidates",
            "dependencies",
            "upstream_suppliers",
        ):
            if isinstance(payload.get(key), list):
                rows = payload[key]
                break
        if rows is None and (
            payload.get("supplier_name") or payload.get("name") or payload.get("company")
        ):
            rows = [payload]
    else:
        rows = payload
    if not isinstance(rows, list):
        return []
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        supplier_name = str(row.get("supplier_name") or "").strip()
        if not supplier_name:
            supplier_name = str(row.get("name") or row.get("company") or "").strip()
        if not supplier_name:
            continue
        out.append(
            {
                "requirement_node_id": str(row.get("requirement_node_id") or "").strip(),
                "requirement_label": str(
                    row.get("requirement_label")
                    or row.get("requirement")
                    or row.get("component")
                    or ""
                ).strip(),
                "supplier_name": supplier_name[:120],
                "ticker": _clean_ticker(row.get("ticker")),
                "product_or_service": str(row.get("product_or_service") or "").strip()[:160],
                "confidence": _clamp_float(row.get("confidence"), default=0.55),
                "uncertainty": str(row.get("uncertainty") or "").strip()[:240],
            }
        )
    return out


def _clean_ticker(value: Any) -> str | None:
    if value is None:
        return None
    ticker = str(value).strip().upper()
    if not ticker or ticker in {"N/A", "NA", "NONE", "NULL"}:
        return None
    return ticker[:16]


def _is_seed_company(
    state: SupplyChainExploreState,
    supplier_name: str,
    supplier_id: str,
) -> bool:
    company = state.request.company_name or ""
    ticker = state.request.ticker or ""
    seed_ids = {
        f"company:{_slug(company)}" if company else "",
        f"company:{_slug(ticker)}" if ticker else "",
    }
    seed_names = {
        _slug(company) if company else "",
        _slug(ticker) if ticker else "",
    }
    supplier_key = _slug(supplier_name)
    return supplier_id in seed_ids or supplier_key in seed_names


def _upgrade_existing_edge_with_evidence(
    state: SupplyChainExploreState,
    *,
    edge_id: str,
    evidence_id: str,
    confidence: float,
    provider: str,
    query: str,
) -> None:
    for index, edge in enumerate(state.links):
        if edge.edge_id != edge_id:
            continue
        evidence_ids = sorted({*edge.evidence_ids, evidence_id})
        state.links[index] = edge.model_copy(
            update={
                "relation_type": "supplied_by",
                "confidence": max(edge.confidence, confidence),
                "evidence_ids": evidence_ids,
                "metadata": {
                    **edge.metadata,
                    "provider": provider,
                    "query": query,
                    "search_confirmed": True,
                },
            }
        )
        return


def _clamp_float(value: Any, *, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return min(1.0, max(0.0, parsed))


def _supplier_candidates_from_tool_events(
    *,
    requirement: SupplyChainNode,
    result: Any,
) -> tuple[list[SupplierCandidate], list[NormalizedSupplyChainEvidence]]:
    candidates: list[SupplierCandidate] = []
    evidence_rows: list[NormalizedSupplyChainEvidence] = []
    for event in result.tool_events:
        if event.status != "success":
            continue
        payload = _parse_tool_payload(event.result_summary)
        if not payload:
            continue
        data = payload.get("data", payload)
        tool_name = payload.get("tool", event.tool_name)
        search_rows = _search_rows_from_tool_data(tool_name, data)
        for index, row in enumerate(search_rows):
            text = " ".join(
                str(row.get(key) or "") for key in ("title", "snippet", "url")
            )
            supplier = _supplier_from_text(text)
            if supplier is None:
                continue
            evidence_dict = build_evidence_from_search(
                {
                    "url": row.get("url", ""),
                    "title": row.get("title", ""),
                    "snippet": row.get("snippet", ""),
                },
                query=str(row.get("query") or requirement.label),
            )
            is_confirmed = bool(evidence_dict.pop("is_confirmed", False))
            evidence = NormalizedSupplyChainEvidence.model_validate(evidence_dict)
            evidence_rows.append(evidence)
            supplier_name, ticker = supplier
            candidates.append(
                SupplierCandidate(
                    supplier_name=supplier_name,
                    ticker=ticker,
                    relation_type="supplied_by" if is_confirmed else "hypothesized",
                    product_or_service=requirement.label,
                    evidence_ids=[evidence.evidence_id] if is_confirmed else [],
                    confidence=evidence.confidence,
                    uncertainty=(
                        None if is_confirmed
                        else "tool result did not include enough source-backed evidence"
                    ),
                    source_requirement_node_id=requirement.node_id,
                )
            )
            if index + 1 >= 10:
                break
    return candidates, evidence_rows


def _parse_tool_payload(text: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _search_rows_from_tool_data(tool_name: str, data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        return []
    rows: list[dict[str, Any]] = []
    if tool_name == "web_search":
        query = str(data.get("query") or "")
        for row in data.get("results", []) or []:
            if isinstance(row, dict):
                rows.append({**row, "query": query})
    elif tool_name == "search_and_fetch":
        search = data.get("search", {})
        if isinstance(search, dict):
            query = str(search.get("query") or "")
            for row in search.get("results", []) or []:
                if isinstance(row, dict):
                    rows.append({**row, "query": query})
        for page in data.get("fetched_pages", []) or []:
            if isinstance(page, dict):
                rows.append(
                    {
                        "url": page.get("url", ""),
                        "title": page.get("title", ""),
                        "snippet": page.get("description") or page.get("content", ""),
                        "query": query if "query" in locals() else "",
                    }
                )
    elif tool_name == "transcript_lookup":
        turns = data.get("turns", []) or []
        snippet = " ".join(
            str(turn.get("text") or turn.get("content") or "")
            for turn in turns[:3]
            if isinstance(turn, dict)
        )
        rows.append(
            {
                "url": data.get("url", ""),
                "title": data.get("title", "Transcript"),
                "snippet": snippet,
                "query": data.get("ticker", ""),
            }
        )
    return rows


def _append_unique_evidence(
    state: SupplyChainExploreState,
    evidence_rows: list[NormalizedSupplyChainEvidence],
) -> None:
    existing = {row.evidence_id for row in state.evidence}
    for row in evidence_rows:
        if row.evidence_id in existing:
            continue
        state.evidence.append(row)
        existing.add(row.evidence_id)
        _increment_metric(state, "evidence_row_count")


def _append_unique_candidates(
    state: SupplyChainExploreState,
    candidates: list[SupplierCandidate],
) -> None:
    existing = {
        (
            candidate.source_requirement_node_id,
            candidate.supplier_name.lower(),
            candidate.product_or_service,
        )
        for candidate in state.llm_supplier_candidates
    }
    for candidate in candidates:
        key = (
            candidate.source_requirement_node_id,
            candidate.supplier_name.lower(),
            candidate.product_or_service,
        )
        if key in existing:
            continue
        state.llm_supplier_candidates.append(candidate)
        existing.add(key)
        _increment_metric(state, "candidate_count")


def _increment_metric(
    state: SupplyChainExploreState,
    name: str,
    amount: int = 1,
) -> None:
    state.metrics[name] = state.metrics.get(name, 0) + amount


__all__ = ["SupplyChainSupplierDiscoveryStep"]
