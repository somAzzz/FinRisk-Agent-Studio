# Step 05 - SearchRouter、网页抓取和缓存

## 目标

把当前 `web_search`、`web_fetch`、browser exploration 整合为统一 SearchRouter，并为免费/付费搜索 provider 预留接口。

当前代码：

```text
src/tools/web_search.py
src/tools/web_fetch.py
src/tools/router.py
src/browser/*
```

## 需要新增或修改的文件

新增：

```text
src/tools/search_router.py
src/tools/search_cache.py
src/tools/providers/__init__.py
src/tools/providers/base.py
src/tools/providers/duckduckgo.py
src/tools/providers/brave.py
src/tools/providers/tavily.py
src/tools/providers/exa.py
src/tools/providers/serper.py
src/tools/providers/serpapi.py
tests/tools/test_search_router.py
tests/tools/test_search_cache.py
```

修改：

```text
src/tools/web_search.py
src/tools/router.py
src/config.py
```

## Search Provider 抽象

```python
class SearchProvider(Protocol):
    provider_name: str

    def search(
        self,
        query: str,
        max_results: int = 5,
        time_range: Literal["d", "w", "m", "y", None] = None,
    ) -> SearchResponse:
        ...
```

Schema：

```python
class SearchResult(BaseModel):
    title: str
    url: str
    snippet: str = ""
    published_at: datetime | None = None
    source: str | None = None
    rank: int
    metadata: dict[str, Any] = Field(default_factory=dict)

class SearchResponse(BaseModel):
    provider: str
    query: str
    retrieved_at: datetime
    results: list[SearchResult]
    raw: dict[str, Any] | None = None
```

## SearchRouter 设计

```python
class SearchRouter:
    def __init__(
        self,
        providers: Sequence[SearchProvider] | None = None,
        cache: SearchCache | None = None,
    ):
        ...

    def search(
        self,
        query: str,
        intent: SearchIntent = "general",
        max_results: int = 5,
        time_range: TimeRange = None,
    ) -> SearchResponse:
        ...
```

Intent：

```python
SearchIntent = Literal[
    "general",
    "news",
    "sec",
    "ir",
    "transcript",
    "semantic",
    "agent_research",
    "verification",
]
```

默认路由：

- `sec`：后续接 SEC search。
- `ir`：优先公司 IR 域名搜索。
- `general/news`：Brave/Serper/DuckDuckGo。
- `semantic`：Exa。
- `agent_research`：Tavily。
- `verification`：SerpApi 或 Brave。

如果未配置付费 API key，自动 fallback 到 DuckDuckGo。

## Cache 设计

简单文件或 SQLite cache 均可。推荐 SQLite，便于 TTL 和去重。

```python
class SearchCache:
    def get(self, provider: str, query: str, params_hash: str) -> SearchResponse | None:
        ...

    def set(self, response: SearchResponse, ttl_seconds: int) -> None:
        ...
```

cache key 包含：

- provider
- query
- max_results
- time_range
- intent

## Web Fetch 整合

现有 `web_fetch(url)` 保留，但 SearchRouter 应提供：

```python
def fetch_search_results(
    self,
    response: SearchResponse,
    max_pages: int = 3,
) -> list[WebFetchResult]:
    ...
```

要求：

- 跳过重复 URL。
- 跳过黑名单域名。
- 失败时记录 error，不中断整个批次。
- 每个 fetch result 可转换成 `Evidence`。

## Provider 实现优先级

第一阶段必须实现：

- DuckDuckGoProvider：包装现有 `web_search` 能力。
- SearchRouter fallback。
- SearchCache。

第二阶段可实现：

- BraveProvider
- TavilyProvider
- ExaProvider
- SerperProvider
- SerpApiProvider

付费 provider 在没有 API key 时不应失败整个系统，应标记 unavailable。

## 测试策略

测试覆盖：

- SearchRouter 在无 API key 时 fallback 到 DuckDuckGo。
- cache hit 不调用 provider。
- cache miss 调用 provider 并写入 cache。
- provider error 时 fallback。
- search result 可转换为 Evidence。
- `web_fetch` 批量失败不影响其它 URL。

## 验收标准

- 原有 `web_search()` 测试继续通过。
- 新的 `SearchRouter.search()` 可返回统一 `SearchResponse`。
- 不配置任何付费 key 时仍可工作。
- cache 可关闭，方便测试。

## 给执行助手的注意事项

- 不要在 provider 中打印 API key。
- 不要把搜索 provider 的原始 response 直接暴露给 Agent，必须转统一 schema。
- 当前项目已有 `src/tools/router.py`，不要直接大改破坏测试；可以逐步让它调用新的 `SearchRouter`。

