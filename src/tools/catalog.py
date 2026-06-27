"""LLM-visible project tool catalog.

The catalog exposes a small, safe set of read-only tools as
OpenAI-compatible function schemas. Provider-specific search engines stay
behind ``SearchRouter`` so LLMs choose the research action, not raw clients.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel

from src.tools.search_router import SearchRouter

ToolSchema = dict[str, Any]
ToolMap = dict[str, Callable[..., Any]]

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


@dataclass(frozen=True)
class ToolCatalog:
    """OpenAI-compatible tool schemas plus executable function map."""

    tools: list[ToolSchema]
    tool_map: ToolMap

    def select(self, names: list[str] | tuple[str, ...]) -> ToolCatalog:
        """Return a catalog containing only the requested tool names."""
        allowed = set(names)
        return ToolCatalog(
            tools=[
                tool for tool in self.tools
                if tool.get("function", {}).get("name") in allowed
            ],
            tool_map={
                name: func for name, func in self.tool_map.items()
                if name in allowed
            },
        )

    @property
    def names(self) -> list[str]:
        """Return tool names in schema order."""
        return [
            str(tool.get("function", {}).get("name"))
            for tool in self.tools
        ]


def build_project_tool_catalog(
    *,
    search_router: SearchRouter | None = None,
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
        return _jsonable(response)

    def web_fetch(url: str) -> dict[str, Any]:
        from src.tools.web_fetch import web_fetch_sync

        return _jsonable(web_fetch_sync(url))

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
            "search": _jsonable(response),
            "fetched_pages": _jsonable(fetched),
        }

    return ToolCatalog(
        tools=[WEB_SEARCH_SCHEMA, WEB_FETCH_SCHEMA, SEARCH_AND_FETCH_SCHEMA],
        tool_map={
            "web_search": web_search,
            "web_fetch": web_fetch,
            "search_and_fetch": search_and_fetch,
        },
    )


WEB_SEARCH_SCHEMA: ToolSchema = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": (
            "Search the web through the project's SearchRouter. Use this for "
            "current facts, market news, company research, and source discovery. "
            "Prefer provider='auto' unless the user explicitly asks for one."
        ),
        "parameters": {
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
        },
    },
}

WEB_FETCH_SCHEMA: ToolSchema = {
    "type": "function",
    "function": {
        "name": "web_fetch",
        "description": (
            "Fetch a specific URL and return metadata plus extracted Markdown. "
            "Use this after web_search when a result URL looks relevant."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "HTTP or HTTPS URL to fetch.",
                }
            },
            "required": ["url"],
        },
    },
}

SEARCH_AND_FETCH_SCHEMA: ToolSchema = {
    "type": "function",
    "function": {
        "name": "search_and_fetch",
        "description": (
            "Search the web and fetch the top non-blacklisted result pages. "
            "Use when the answer needs article/page content, not just snippets."
        ),
        "parameters": {
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
        },
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


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, int(value)))


def _jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if hasattr(value, "__dict__"):
        return {
            key: _jsonable(item)
            for key, item in vars(value).items()
            if not key.startswith("_")
        }
    return value


__all__ = [
    "SEARCH_AND_FETCH_SCHEMA",
    "WEB_FETCH_SCHEMA",
    "WEB_SEARCH_SCHEMA",
    "ToolCatalog",
    "build_project_tool_catalog",
]
