from types import SimpleNamespace

from src.tools.catalog import build_project_tool_catalog


class FakeRouter:
    def __init__(self) -> None:
        self.search_calls: list[dict] = []
        self.fetch_calls: list[dict] = []

    def search(self, query, intent="general", max_results=5, time_range=None):
        self.search_calls.append(
            {
                "query": query,
                "intent": intent,
                "max_results": max_results,
                "time_range": time_range,
            }
        )
        return SimpleNamespace(
            provider="fake",
            query=query,
            retrieved_at="2026-06-27T00:00:00Z",
            results=[
                SimpleNamespace(
                    title="Result",
                    url="https://example.com/a",
                    snippet="Snippet",
                    rank=1,
                )
            ],
        )

    def fetch_search_results(self, response, max_pages=3):
        self.fetch_calls.append({"response": response, "max_pages": max_pages})
        return [
            SimpleNamespace(
                url="https://example.com/a",
                content="Fetched body",
                status_code=200,
                error=None,
            )
        ]


def test_project_tool_catalog_exposes_openai_compatible_schemas() -> None:
    catalog = build_project_tool_catalog(search_router=FakeRouter())  # type: ignore[arg-type]

    assert catalog.names == ["web_search", "web_fetch", "search_and_fetch"]
    assert all(tool["type"] == "function" for tool in catalog.tools)
    assert catalog.tools[0]["function"]["parameters"]["required"] == ["query"]


def test_project_tool_catalog_web_search_uses_router() -> None:
    router = FakeRouter()
    catalog = build_project_tool_catalog(search_router=router)  # type: ignore[arg-type]

    result = catalog.tool_map["web_search"](
        query="AAPL recent risk",
        intent="news",
        max_results=99,
        time_range="w",
    )

    assert router.search_calls == [
        {
            "query": "AAPL recent risk",
            "intent": "news",
            "max_results": 10,
            "time_range": "w",
        }
    ]
    assert result["provider"] == "fake"
    assert result["results"][0]["url"] == "https://example.com/a"


def test_project_tool_catalog_search_and_fetch_uses_router_fetch() -> None:
    router = FakeRouter()
    catalog = build_project_tool_catalog(search_router=router)  # type: ignore[arg-type]

    result = catalog.tool_map["search_and_fetch"](
        query="AAPL suppliers",
        max_pages=99,
    )

    assert router.search_calls[0]["query"] == "AAPL suppliers"
    assert router.fetch_calls[0]["max_pages"] == 5
    assert result["search"]["provider"] == "fake"
    assert result["fetched_pages"][0]["content"] == "Fetched body"


def test_project_tool_catalog_select_filters_tools_and_map() -> None:
    catalog = build_project_tool_catalog(search_router=FakeRouter())  # type: ignore[arg-type]

    selected = catalog.select(["web_search"])

    assert selected.names == ["web_search"]
    assert list(selected.tool_map) == ["web_search"]
