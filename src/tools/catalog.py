"""LLM-visible project tool catalog.

The catalog exposes a small, safe set of read-only tools as
OpenAI-compatible function schemas. Provider-specific search engines stay
behind ``SearchRouter`` so LLMs choose the research action, not raw clients.
"""

from __future__ import annotations

import asyncio
import inspect
import threading
from datetime import date
from typing import Any, Literal

from src.tools.contracts import ProjectTool, ToolCatalog, ToolSchema, jsonable
from src.tools.search_router import SearchRouter

SearchProviderChoice = Literal["auto", "duckduckgo", "brave", "tavily"]
TimeRangeChoice = Literal["d", "w", "m", "y", None]

SEARCH_INTENTS = [
    "general",
    "news",
    "sec",
    "ir",
    "transcript",
    "semantic",
    "agent_research",
    "verification",
    "product_supply_chain",
    "supplier_discovery",
    "component_supplier",
    "cloud_dependency",
    "datacenter_power",
    "semiconductor_supply_chain",
    "supply_chain",
    "policy",
    "geopolitical",
]

READ_SCOPES = frozenset(
    {
        "default",
        "company_research",
        "finrisk_market",
        "supply_chain",
    }
)


def build_project_tool_catalog(
    *,
    search_router: SearchRouter | None = None,
    ticker_resolver: Any | None = None,
    filing_fetcher: Any | None = None,
    transcript_provider: Any | None = None,
    metrics_fetcher: Any | None = None,
    company_facts_fetcher: Any | None = None,
    graph_backend: Any | None = None,
    browser_explorer: Any | None = None,
    scope: str | None = "default",
) -> ToolCatalog:
    """Build the default read-only project tools for LLM tool calling."""
    router = search_router or SearchRouter()

    def web_search(
        query: str,
        intent: str = "general",
        max_results: int = 5,
        time_range: TimeRangeChoice = None,
        provider: SearchProviderChoice = "auto",
    ) -> dict[str, Any]:
        active_router = _router_for_provider(provider, router)
        response = active_router.search(
            query=query,
            intent=intent,  # type: ignore[arg-type]
            max_results=_clamp(max_results, 1, 10),
            time_range=time_range,
        )
        return jsonable(response)

    def web_fetch(url: str) -> dict[str, Any]:
        from src.tools.web_fetch import web_fetch_sync

        return jsonable(web_fetch_sync(url))

    def search_and_fetch(
        query: str,
        intent: str = "general",
        max_results: int = 5,
        max_pages: int = 3,
        time_range: TimeRangeChoice = None,
        provider: SearchProviderChoice = "auto",
    ) -> dict[str, Any]:
        active_router = _router_for_provider(provider, router)
        response = active_router.search(
            query=query,
            intent=intent,  # type: ignore[arg-type]
            max_results=_clamp(max_results, 1, 10),
            time_range=time_range,
        )
        fetched = active_router.fetch_search_results(
            response,
            max_pages=_clamp(max_pages, 1, 5),
        )
        return {
            "search": jsonable(response),
            "fetched_pages": jsonable(fetched),
        }

    def sec_list_filings(
        ticker: str,
        form_types: list[str] | None = None,
        since: str | None = None,
        limit: int = 5,
    ) -> dict[str, Any]:
        resolver = ticker_resolver or _default_ticker_resolver()
        fetcher = filing_fetcher or _default_filing_fetcher()
        ident = resolver.resolve(ticker)
        if ident is None:
            return {"ticker": ticker.upper(), "filings": [], "error": "ticker not resolved"}
        since_date = _parse_date(since)
        filings = fetcher.list_filings(
            ident.cik,
            form_types=tuple(form_types or ["10-K", "10-Q", "8-K"]),
            since=since_date,
            limit=_clamp(limit, 1, 20),
        )
        return {
            "ticker": ident.ticker,
            "cik": ident.cik,
            "company_name": ident.name,
            "filings": jsonable(filings),
        }

    def sec_fetch_filing(
        ticker: str,
        accession_number: str | None = None,
        form_types: list[str] | None = None,
        section: str = "full_text",
    ) -> dict[str, Any]:
        resolver = ticker_resolver or _default_ticker_resolver()
        fetcher = filing_fetcher or _default_filing_fetcher()
        ident = resolver.resolve(ticker)
        if ident is None:
            return {"ticker": ticker.upper(), "error": "ticker not resolved"}
        filings = fetcher.list_filings(
            ident.cik,
            form_types=tuple(form_types or ["10-K", "10-Q", "8-K"]),
            limit=20,
        )
        selected = None
        for filing in filings:
            if accession_number is None or filing.accession_number == accession_number:
                selected = filing
                break
        if selected is None:
            return {
                "ticker": ident.ticker,
                "cik": ident.cik,
                "error": "filing not found",
            }
        record = fetcher.fetch_filing(selected)
        section_key = _canonical_section(section)
        text = record.sections.get(section_key)
        if text is None:
            text = record.sections.get("full_text", "")
            section_key = "full_text"
        return {
            "ticker": ident.ticker,
            "cik": ident.cik,
            "accession_number": record.accession_number,
            "form_type": record.form_type,
            "filing_date": record.filing_date.isoformat(),
            "section": section_key,
            "text": text,
            "source_url": record.url,
            "metadata": record.metadata,
        }

    def transcript_lookup(
        ticker: str,
        year: int,
        quarter: int,
        section: str = "all",
    ) -> dict[str, Any]:
        provider = transcript_provider or _default_transcript_provider()
        transcript = provider.get_transcript(ticker.upper(), int(year), int(quarter))
        turns = jsonable(transcript.turns)
        if section != "all":
            turns = [
                turn for turn in turns
                if isinstance(turn, dict) and turn.get("section") == section
            ]
        return {
            "ticker": transcript.ticker,
            "company_name": transcript.company_name,
            "year": transcript.year,
            "quarter": transcript.quarter,
            "provider": transcript.provider,
            "transcript_id": transcript.transcript_id,
            "title": transcript.title,
            "published_at": (
                transcript.published_at.isoformat()
                if transcript.published_at else None
            ),
            "url": transcript.url,
            "section": section,
            "turns": turns,
        }

    def financial_metrics_lookup(
        ticker: str,
        metrics: list[str] | None = None,
    ) -> dict[str, Any]:
        fetcher = metrics_fetcher or _default_metrics_fetcher()
        values = fetcher(ticker.upper())
        if metrics:
            wanted = set(metrics)
            values = {
                key: value for key, value in values.items()
                if key in wanted
            }
        return {
            "ticker": ticker.upper(),
            "source": getattr(fetcher, "__name__", "financial_metrics"),
            "metrics": values,
        }

    def xbrl_fact_lookup(
        ticker: str,
        concepts: list[str],
        unit: str = "USD",
        limit: int = 5,
    ) -> dict[str, Any]:
        resolver = ticker_resolver or _default_ticker_resolver()
        facts_fetcher = company_facts_fetcher or _default_company_facts_fetcher()
        ident = resolver.resolve(ticker)
        if ident is None:
            return {"ticker": ticker.upper(), "facts": [], "error": "ticker not resolved"}
        raw_facts = facts_fetcher(ident.cik)
        from src.data.xbrl import extract_metric

        out: list[dict[str, Any]] = []
        for concept in concepts:
            rows = extract_metric(raw_facts, concept=concept, unit=unit)
            out.extend(jsonable(rows[: _clamp(limit, 1, 20)]))
        return {
            "ticker": ident.ticker,
            "cik": ident.cik,
            "unit": unit,
            "facts": out,
        }

    def graph_query(
        entity: str,
        ticker: str | None = None,
        max_hops: int = 3,
        allowed_edge_types: list[str] | None = None,
    ) -> dict[str, Any]:
        context = _graph_context(
            entity=entity,
            ticker=ticker,
            max_hops=max_hops,
            allowed_edge_types=allowed_edge_types,
        )
        paths = (
            graph_backend.retrieve(context)
            if graph_backend is not None
            else _fixture_graph_paths(context)
        )
        return {
            "context": jsonable(context),
            "paths": jsonable(paths),
        }

    def graph_path_search(
        source_entity: str,
        target_entity: str | None = None,
        ticker: str | None = None,
        max_hops: int = 3,
        allowed_edge_types: list[str] | None = None,
    ) -> dict[str, Any]:
        context = _graph_context(
            entity=source_entity,
            ticker=ticker,
            max_hops=max_hops,
            allowed_edge_types=allowed_edge_types,
        )
        paths = (
            graph_backend.retrieve(context)
            if graph_backend is not None
            else _fixture_graph_paths(context)
        )
        if target_entity:
            target = target_entity.lower()
            paths = [
                path for path in paths
                if target in _path_text(path).lower()
            ]
        return {
            "context": jsonable(context),
            "target_entity": target_entity,
            "paths": jsonable(paths),
        }

    def browser_explore(
        goal: str,
        initial_urls: list[str] | None = None,
        max_steps: int = 5,
    ) -> dict[str, Any]:
        explorer = browser_explorer or _default_browser_explorer(max_steps=max_steps)
        result = explorer.explore(goal, initial_urls=initial_urls)
        state = _run_sync(result) if inspect.isawaitable(result) else result
        findings = [
            jsonable(finding)
            for finding in getattr(state, "findings", [])
        ]
        return {
            "goal": goal,
            "current_step": getattr(state, "current_step", None),
            "findings": findings,
            "visited_urls": jsonable(getattr(state, "visited_urls", [])),
        }

    catalog = ToolCatalog(
        project_tools=(
            ProjectTool(
                name="web_search",
                description=WEB_SEARCH_DESCRIPTION,
                parameters=WEB_SEARCH_PARAMETERS,
                callable=web_search,
                risk_level="read_only",
                scopes=READ_SCOPES,
                evidence_kind="web",
            ),
            ProjectTool(
                name="web_fetch",
                description=WEB_FETCH_DESCRIPTION,
                parameters=WEB_FETCH_PARAMETERS,
                callable=web_fetch,
                risk_level="read_only",
                scopes=READ_SCOPES,
                evidence_kind="web",
            ),
            ProjectTool(
                name="search_and_fetch",
                description=SEARCH_AND_FETCH_DESCRIPTION,
                parameters=SEARCH_AND_FETCH_PARAMETERS,
                callable=search_and_fetch,
                risk_level="read_only",
                scopes=READ_SCOPES,
                evidence_kind="web",
                max_result_chars=18000,
            ),
            ProjectTool(
                name="sec_list_filings",
                description=SEC_LIST_FILINGS_DESCRIPTION,
                parameters=SEC_LIST_FILINGS_PARAMETERS,
                callable=sec_list_filings,
                risk_level="read_only",
                scopes=frozenset({"company_research", "finrisk_filing"}),
                evidence_kind="filing",
            ),
            ProjectTool(
                name="sec_fetch_filing",
                description=SEC_FETCH_FILING_DESCRIPTION,
                parameters=SEC_FETCH_FILING_PARAMETERS,
                callable=sec_fetch_filing,
                risk_level="read_only",
                scopes=frozenset({"company_research", "finrisk_filing", "supply_chain"}),
                evidence_kind="filing",
                max_result_chars=24000,
            ),
            ProjectTool(
                name="transcript_lookup",
                description=TRANSCRIPT_LOOKUP_DESCRIPTION,
                parameters=TRANSCRIPT_LOOKUP_PARAMETERS,
                callable=transcript_lookup,
                risk_level="read_only",
                scopes=frozenset({"company_research", "transcript_analysis", "supply_chain", "finrisk_market"}),
                evidence_kind="transcript",
                max_result_chars=20000,
            ),
            ProjectTool(
                name="financial_metrics_lookup",
                description=FINANCIAL_METRICS_LOOKUP_DESCRIPTION,
                parameters=FINANCIAL_METRICS_LOOKUP_PARAMETERS,
                callable=financial_metrics_lookup,
                risk_level="read_only",
                scopes=frozenset({"company_research", "supply_chain", "finrisk_market"}),
                evidence_kind="financial_metric",
            ),
            ProjectTool(
                name="xbrl_fact_lookup",
                description=XBRL_FACT_LOOKUP_DESCRIPTION,
                parameters=XBRL_FACT_LOOKUP_PARAMETERS,
                callable=xbrl_fact_lookup,
                risk_level="read_only",
                scopes=frozenset({"company_research", "finrisk_filing"}),
                evidence_kind="financial_metric",
            ),
            ProjectTool(
                name="graph_query",
                description=GRAPH_QUERY_DESCRIPTION,
                parameters=GRAPH_QUERY_PARAMETERS,
                callable=graph_query,
                risk_level="read_only",
                scopes=frozenset({"company_research", "finrisk_market", "supply_chain"}),
                evidence_kind="graph_path",
            ),
            ProjectTool(
                name="graph_path_search",
                description=GRAPH_PATH_SEARCH_DESCRIPTION,
                parameters=GRAPH_PATH_SEARCH_PARAMETERS,
                callable=graph_path_search,
                risk_level="read_only",
                scopes=frozenset({"company_research", "finrisk_market", "supply_chain"}),
                evidence_kind="graph_path",
            ),
            ProjectTool(
                name="browser_explore",
                description=BROWSER_EXPLORE_DESCRIPTION,
                parameters=BROWSER_EXPLORE_PARAMETERS,
                callable=browser_explore,
                risk_level="interactive",
                scopes=frozenset({"company_research", "finrisk_market"}),
                evidence_kind="browser",
                max_result_chars=18000,
            ),
        )
    )
    return catalog if scope is None else catalog.for_scope(scope)


WEB_SEARCH_DESCRIPTION = (
    "Search the web through the project's SearchRouter. Use this for "
    "current facts, market news, company research, and source discovery. "
    "Prefer provider='auto' unless the user explicitly asks for one."
)

WEB_SEARCH_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "Search query, preferably concise English.",
        },
        "intent": {
            "type": "string",
            "enum": SEARCH_INTENTS,
            "description": "Research intent used for query templating.",
            "default": "general",
        },
        "max_results": {
            "type": "integer",
            "minimum": 1,
            "maximum": 10,
            "default": 5,
        },
        "time_range": {
            "type": ["string", "null"],
            "enum": ["d", "w", "m", "y", None],
            "description": "'d'=day, 'w'=week, 'm'=month, 'y'=year.",
            "default": None,
        },
        "provider": {
            "type": "string",
            "enum": ["auto", "duckduckgo", "brave", "tavily"],
            "default": "auto",
        },
    },
    "required": ["query"],
}

WEB_FETCH_DESCRIPTION = (
    "Fetch a specific URL and return metadata plus extracted Markdown. "
    "Use this after web_search when a result URL looks relevant."
)

WEB_FETCH_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "url": {
            "type": "string",
            "description": "HTTP or HTTPS URL to fetch.",
        }
    },
    "required": ["url"],
}

SEARCH_AND_FETCH_DESCRIPTION = (
    "Search the web and fetch the top non-blacklisted result pages. "
    "Use when the answer needs article/page content, not just snippets."
)

SEARCH_AND_FETCH_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {"type": "string"},
        "intent": {
            "type": "string",
            "enum": SEARCH_INTENTS,
            "default": "general",
        },
        "max_results": {
            "type": "integer",
            "minimum": 1,
            "maximum": 10,
            "default": 5,
        },
        "max_pages": {
            "type": "integer",
            "minimum": 1,
            "maximum": 5,
            "default": 3,
        },
        "time_range": {
            "type": ["string", "null"],
            "enum": ["d", "w", "m", "y", None],
            "default": None,
        },
        "provider": {
            "type": "string",
            "enum": ["auto", "duckduckgo", "brave", "tavily"],
            "default": "auto",
        },
    },
    "required": ["query"],
}

SEC_LIST_FILINGS_DESCRIPTION = (
    "List recent SEC filings for a ticker. Use before sec_fetch_filing when "
    "you need to inspect current or historical 10-K, 10-Q, or 8-K filings."
)

SEC_LIST_FILINGS_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "ticker": {"type": "string"},
        "form_types": {
            "type": ["array", "null"],
            "items": {"type": "string"},
            "default": ["10-K", "10-Q", "8-K"],
        },
        "since": {
            "type": ["string", "null"],
            "description": "Optional YYYY-MM-DD lower bound.",
            "default": None,
        },
        "limit": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5},
    },
    "required": ["ticker"],
}

SEC_FETCH_FILING_DESCRIPTION = (
    "Fetch a SEC filing section for a ticker. Use accession_number from "
    "sec_list_filings when available; otherwise the newest matching filing "
    "is fetched."
)

SEC_FETCH_FILING_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "ticker": {"type": "string"},
        "accession_number": {"type": ["string", "null"], "default": None},
        "form_types": {
            "type": ["array", "null"],
            "items": {"type": "string"},
            "default": ["10-K", "10-Q", "8-K"],
        },
        "section": {
            "type": "string",
            "enum": [
                "full_text",
                "1",
                "1A",
                "7",
                "7A",
                "section_1",
                "section_1a",
                "section_7",
                "section_7a",
            ],
            "default": "full_text",
        },
    },
    "required": ["ticker"],
}

TRANSCRIPT_LOOKUP_DESCRIPTION = (
    "Fetch one earnings-call transcript for management commentary, Q&A, "
    "guidance, demand, margin, and supply-chain signals."
)

TRANSCRIPT_LOOKUP_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "ticker": {"type": "string"},
        "year": {"type": "integer"},
        "quarter": {"type": "integer", "minimum": 1, "maximum": 4},
        "section": {
            "type": "string",
            "enum": ["all", "prepared_remarks", "qa", "unknown"],
            "default": "all",
        },
    },
    "required": ["ticker", "year", "quarter"],
}

FINANCIAL_METRICS_LOOKUP_DESCRIPTION = (
    "Lookup latest available financial ratios or metrics for a ticker. "
    "Use to cross-check textual claims against quantitative signals."
)

FINANCIAL_METRICS_LOOKUP_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "ticker": {"type": "string"},
        "metrics": {
            "type": ["array", "null"],
            "items": {"type": "string"},
            "default": None,
        },
    },
    "required": ["ticker"],
}

XBRL_FACT_LOOKUP_DESCRIPTION = (
    "Fetch SEC XBRL company facts for specific concepts such as Revenues, "
    "GrossProfit, NetIncomeLoss, or CapitalExpenditures."
)

XBRL_FACT_LOOKUP_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "ticker": {"type": "string"},
        "concepts": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
        },
        "unit": {"type": "string", "default": "USD"},
        "limit": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5},
    },
    "required": ["ticker", "concepts"],
}

GRAPH_QUERY_DESCRIPTION = (
    "Read bounded graph paths around an entity using the project's graph "
    "retriever. This tool accepts structured filters only; it does not "
    "accept raw Cypher or write graph data."
)

GRAPH_QUERY_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "entity": {
            "type": "string",
            "description": "Company/entity id or ticker, e.g. company:AAPL or AAPL.",
        },
        "ticker": {"type": ["string", "null"], "default": None},
        "max_hops": {
            "type": "integer",
            "minimum": 1,
            "maximum": 4,
            "default": 3,
        },
        "allowed_edge_types": {
            "type": ["array", "null"],
            "items": {"type": "string"},
            "default": None,
        },
    },
    "required": ["entity"],
}

GRAPH_PATH_SEARCH_DESCRIPTION = (
    "Search bounded graph paths from a source entity, optionally filtered "
    "to paths mentioning a target entity. No raw Cypher is accepted."
)

GRAPH_PATH_SEARCH_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "source_entity": {"type": "string"},
        "target_entity": {"type": ["string", "null"], "default": None},
        "ticker": {"type": ["string", "null"], "default": None},
        "max_hops": {
            "type": "integer",
            "minimum": 1,
            "maximum": 4,
            "default": 3,
        },
        "allowed_edge_types": {
            "type": ["array", "null"],
            "items": {"type": "string"},
            "default": None,
        },
    },
    "required": ["source_entity"],
}

BROWSER_EXPLORE_DESCRIPTION = (
    "Run the project's bounded MarketExplorer sub-agent for pages that need "
    "browser exploration. This wraps navigation internally and does not expose "
    "low-level click, type, or scroll actions."
)

BROWSER_EXPLORE_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "goal": {"type": "string"},
        "initial_urls": {
            "type": ["array", "null"],
            "items": {"type": "string"},
            "default": None,
        },
        "max_steps": {
            "type": "integer",
            "minimum": 1,
            "maximum": 10,
            "default": 5,
        },
    },
    "required": ["goal"],
}

WEB_SEARCH_SCHEMA: ToolSchema = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": WEB_SEARCH_DESCRIPTION,
        "parameters": WEB_SEARCH_PARAMETERS,
    },
}

WEB_FETCH_SCHEMA: ToolSchema = {
    "type": "function",
    "function": {
        "name": "web_fetch",
        "description": WEB_FETCH_DESCRIPTION,
        "parameters": WEB_FETCH_PARAMETERS,
    },
}

SEARCH_AND_FETCH_SCHEMA: ToolSchema = {
    "type": "function",
    "function": {
        "name": "search_and_fetch",
        "description": SEARCH_AND_FETCH_DESCRIPTION,
        "parameters": SEARCH_AND_FETCH_PARAMETERS,
    },
}

SEC_LIST_FILINGS_SCHEMA: ToolSchema = {
    "type": "function",
    "function": {
        "name": "sec_list_filings",
        "description": SEC_LIST_FILINGS_DESCRIPTION,
        "parameters": SEC_LIST_FILINGS_PARAMETERS,
    },
}

SEC_FETCH_FILING_SCHEMA: ToolSchema = {
    "type": "function",
    "function": {
        "name": "sec_fetch_filing",
        "description": SEC_FETCH_FILING_DESCRIPTION,
        "parameters": SEC_FETCH_FILING_PARAMETERS,
    },
}

TRANSCRIPT_LOOKUP_SCHEMA: ToolSchema = {
    "type": "function",
    "function": {
        "name": "transcript_lookup",
        "description": TRANSCRIPT_LOOKUP_DESCRIPTION,
        "parameters": TRANSCRIPT_LOOKUP_PARAMETERS,
    },
}

FINANCIAL_METRICS_LOOKUP_SCHEMA: ToolSchema = {
    "type": "function",
    "function": {
        "name": "financial_metrics_lookup",
        "description": FINANCIAL_METRICS_LOOKUP_DESCRIPTION,
        "parameters": FINANCIAL_METRICS_LOOKUP_PARAMETERS,
    },
}

XBRL_FACT_LOOKUP_SCHEMA: ToolSchema = {
    "type": "function",
    "function": {
        "name": "xbrl_fact_lookup",
        "description": XBRL_FACT_LOOKUP_DESCRIPTION,
        "parameters": XBRL_FACT_LOOKUP_PARAMETERS,
    },
}

GRAPH_QUERY_SCHEMA: ToolSchema = {
    "type": "function",
    "function": {
        "name": "graph_query",
        "description": GRAPH_QUERY_DESCRIPTION,
        "parameters": GRAPH_QUERY_PARAMETERS,
    },
}

GRAPH_PATH_SEARCH_SCHEMA: ToolSchema = {
    "type": "function",
    "function": {
        "name": "graph_path_search",
        "description": GRAPH_PATH_SEARCH_DESCRIPTION,
        "parameters": GRAPH_PATH_SEARCH_PARAMETERS,
    },
}

BROWSER_EXPLORE_SCHEMA: ToolSchema = {
    "type": "function",
    "function": {
        "name": "browser_explore",
        "description": BROWSER_EXPLORE_DESCRIPTION,
        "parameters": BROWSER_EXPLORE_PARAMETERS,
    },
}


def _router_for_provider(provider: str, default_router: SearchRouter) -> SearchRouter:
    if provider == "auto":
        return default_router
    if provider == "duckduckgo":
        from src.tools.providers.duckduckgo import DuckDuckGoProvider

        return SearchRouter(providers=[DuckDuckGoProvider()])
    if provider == "brave":
        from src.tools.providers.brave import BraveProvider

        return SearchRouter(providers=[BraveProvider()])
    if provider == "tavily":
        from src.tools.providers.tavily import TavilyProvider

        return SearchRouter(providers=[TavilyProvider()])
    return default_router


def _default_ticker_resolver() -> Any:
    from src.data.ticker_resolver import TickerResolver

    return TickerResolver()


def _default_filing_fetcher() -> Any:
    from src.data.filing_fetcher import FilingFetcher
    from src.data.sec_client import SECClient

    return FilingFetcher(SECClient())


def _default_transcript_provider() -> Any:
    from src.data.providers.defeatbeta import DefeatBetaProvider

    return DefeatBetaProvider()


def _default_metrics_fetcher() -> Any:
    from src.data.providers.defeatbeta import fetch_financial_metrics_defeatbeta

    return fetch_financial_metrics_defeatbeta


def _default_company_facts_fetcher() -> Any:
    from src.data.sec_client import SECClient

    client = SECClient()
    return client.get_company_facts


def _default_browser_explorer(*, max_steps: int) -> Any:
    from src.browser.config import BrowserConfig
    from src.browser.explorer import MarketExplorer

    return MarketExplorer(browser_config=BrowserConfig(max_steps=_clamp(max_steps, 1, 10)))


def _graph_context(
    *,
    entity: str,
    ticker: str | None,
    max_hops: int,
    allowed_edge_types: list[str] | None,
) -> dict[str, Any]:
    cleaned = entity.strip()
    if cleaned.startswith("company:"):
        company_id = cleaned
        inferred_ticker = cleaned.split(":", 1)[1].upper()
    else:
        inferred_ticker = cleaned.upper()
        company_id = f"company:{inferred_ticker}"
    return {
        "company_id": company_id,
        "ticker": (ticker or inferred_ticker).upper(),
        "max_hops": _clamp(max_hops, 1, 4),
        "allowed_edge_types": allowed_edge_types or [],
    }


def _graph_node(node_id: str, node_type: str, label: str) -> dict[str, Any]:
    return {"node_id": node_id, "node_type": node_type, "label": label}


def _graph_edge(
    source_node_id: str,
    target_node_id: str,
    edge_type: str,
    confidence: float,
) -> dict[str, Any]:
    return {
        "source_node_id": source_node_id,
        "target_node_id": target_node_id,
        "edge_type": edge_type,
        "confidence": confidence,
    }


_GRAPH_NODES: dict[str, dict[str, Any]] = {
    "company:AAPL": _graph_node("company:AAPL", "Company", "Apple Inc."),
    "ticker:AAPL": _graph_node("ticker:AAPL", "Ticker", "AAPL"),
    "supplier:TSMC": _graph_node("supplier:TSMC", "Supplier", "TSMC"),
    "region:Taiwan": _graph_node("region:Taiwan", "Region", "Taiwan"),
    "policy:tariff": _graph_node("policy:tariff", "Policy", "US Tariff Regime"),
    "risk:supply-asia": _graph_node(
        "risk:supply-asia", "Risk", "Asia supply chain"
    ),
    "risk:tariff": _graph_node("risk:tariff", "Risk", "Tariff exposure"),
    "event:taiwan-strait": _graph_node(
        "event:taiwan-strait", "Event", "Taiwan Strait tension"
    ),
}

_GRAPH_EDGES: tuple[dict[str, Any], ...] = (
    _graph_edge("company:AAPL", "ticker:AAPL", "ISSUES", 0.7),
    _graph_edge("company:AAPL", "supplier:TSMC", "DEPENDS_ON", 0.9),
    _graph_edge("supplier:TSMC", "region:Taiwan", "LOCATED_IN", 0.95),
    _graph_edge("region:Taiwan", "event:taiwan-strait", "EXPOSED_TO", 0.6),
    _graph_edge("company:AAPL", "policy:tariff", "EXPOSED_TO", 0.85),
    _graph_edge("policy:tariff", "risk:tariff", "AFFECTS", 0.7),
    _graph_edge("region:Taiwan", "risk:supply-asia", "AFFECTS", 0.6),
)


def _fixture_graph_paths(context: dict[str, Any]) -> list[dict[str, Any]]:
    start = context["company_id"]
    if start not in _GRAPH_NODES:
        return []
    allowed = set(context.get("allowed_edge_types") or [])
    max_hops = int(context.get("max_hops") or 3)
    paths: list[dict[str, Any]] = []

    def dfs(current: str, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> None:
        if edges:
            paths.append(_path_payload(nodes, edges))
        if len(edges) >= max_hops:
            return
        visited = {node["node_id"] for node in nodes}
        for edge in _GRAPH_EDGES:
            if edge["source_node_id"] != current:
                continue
            if allowed and edge["edge_type"] not in allowed:
                continue
            target = edge["target_node_id"]
            if target in visited or target not in _GRAPH_NODES:
                continue
            dfs(target, [*nodes, _GRAPH_NODES[target]], [*edges, edge])

    dfs(start, [_GRAPH_NODES[start]], [])
    return paths


def _path_payload(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "path_text": " -> ".join(str(node["label"]) for node in nodes),
        "nodes": nodes,
        "edges": [
            {
                "source_node_id": edge["source_node_id"],
                "target_node_id": edge["target_node_id"],
                "edge_type": edge["edge_type"],
                "confidence": edge["confidence"],
            }
            for edge in edges
        ],
        "evidence_ids": [],
        "hop_count": len(edges),
    }


def _path_text(path: Any) -> str:
    if isinstance(path, dict):
        return str(path.get("path_text") or "")
    return str(getattr(path, "path_text", ""))


def _run_sync(awaitable: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(awaitable)

    result_box: dict[str, Any] = {}
    error_box: dict[str, BaseException] = {}

    def _worker() -> None:
        try:
            result_box["result"] = asyncio.run(awaitable)
        except BaseException as exc:  # pragma: no cover - defensive thread bridge
            error_box["error"] = exc

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    thread.join()
    if "error" in error_box:
        raise error_box["error"]
    return result_box.get("result")


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, int(value)))


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _canonical_section(section: str) -> str:
    normalized = section.strip().lower().replace("item ", "")
    mapping = {
        "1": "section_1",
        "1a": "section_1a",
        "7": "section_7",
        "7a": "section_7a",
        "section_1": "section_1",
        "section_1a": "section_1a",
        "section_7": "section_7",
        "section_7a": "section_7a",
        "full_text": "full_text",
    }
    return mapping.get(normalized, "full_text")


__all__ = [
    "BROWSER_EXPLORE_PARAMETERS",
    "BROWSER_EXPLORE_SCHEMA",
    "FINANCIAL_METRICS_LOOKUP_PARAMETERS",
    "FINANCIAL_METRICS_LOOKUP_SCHEMA",
    "GRAPH_PATH_SEARCH_PARAMETERS",
    "GRAPH_PATH_SEARCH_SCHEMA",
    "GRAPH_QUERY_PARAMETERS",
    "GRAPH_QUERY_SCHEMA",
    "SEARCH_AND_FETCH_PARAMETERS",
    "SEARCH_AND_FETCH_SCHEMA",
    "SEC_FETCH_FILING_PARAMETERS",
    "SEC_FETCH_FILING_SCHEMA",
    "SEC_LIST_FILINGS_PARAMETERS",
    "SEC_LIST_FILINGS_SCHEMA",
    "TRANSCRIPT_LOOKUP_PARAMETERS",
    "TRANSCRIPT_LOOKUP_SCHEMA",
    "WEB_FETCH_PARAMETERS",
    "WEB_FETCH_SCHEMA",
    "WEB_SEARCH_PARAMETERS",
    "WEB_SEARCH_SCHEMA",
    "XBRL_FACT_LOOKUP_PARAMETERS",
    "XBRL_FACT_LOOKUP_SCHEMA",
    "ProjectTool",
    "ToolCatalog",
    "build_project_tool_catalog",
]
