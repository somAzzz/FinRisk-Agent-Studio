# Web Tools Tiered Routing Implementation Plan

> **Status (2026-06-25):** Implemented via commits `d806528` (Tavily), `150d374` (SearXNG), `7361062` (tier detection), `4d8c0de` (tiered routing), `d9caeca` (router quality fixes). The architecture has since evolved — `src/tools/router.py` is now `src/tools/search_router.py` and the tool layer was factored into `src/tools/providers/` with cache (`src/tools/search_cache.py`). Kept as the historical implementation record of the FinText-LLM tiered routing work.

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Tavily and SearXNG to the web tools system with tiered routing (ddgs for simple queries, tavily for deep search, SearXNG as transparent fallback).

**Architecture:** Tiered routing strategy using keyword-based rule detection before LLM call. ddgs wrapped in try-except with transparent SearXNG fallback. All tools return unified JSON Envelope format.

**Tech Stack:** Python 3.12, httpx, ddgs, trafilatura

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `src/tools/tavily.py` | **Create** | Tavily API wrapper |
| `src/tools/searxng.py` | **Create** | SearXNG transparent fallback |
| `src/tools/router.py` | **Modify** | Tiered routing logic, updated prompt |
| `src/tools/web_search.py` | **Modify** | Add `_ddgs_search` wrapper with try-except |
| `tests/tools/test_tavily.py` | **Create** | Tavily unit tests |
| `tests/tools/test_searxng.py` | **Create** | SearXNG unit tests |
| `tests/tools/test_router.py` | **Create** | Router tier detection tests |

---

## Chunk 1: Tavily Search Tool

**Files:**
- Create: `src/tools/tavily.py`
- Create: `tests/tools/test_tavily.py`

- [ ] **Step 1: Write failing test for tavily_search**

```python
# tests/tools/test_tavily.py
import pytest
from unittest.mock import patch, MagicMock

def test_tavily_search_returns_unified_envelope():
    """Tavily should return JSON Envelope with source='tavily'."""
    with patch("httpx.post") as mock_post:
        mock_post.return_value = MagicMock(
            json=lambda: {
                "results": [
                    {"title": "Test", "url": "https://test.com", "content": "Test content", "published_date": "2026-03-20"}
                ],
                "answer": "Test answer"
            }
        )
        from src.tools.tavily import tavily_search
        result = tavily_search("test query")
        import json
        data = json.loads(result)
        assert data["source"] == "tavily"
        assert data["query_used"] == "test query"
        assert len(data["results"]) == 1
        assert data["results"][0]["body"] == "Test content"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/tools/test_tavily.py::test_tavily_search_returns_unified_envelope -v`
Expected: `ERROR - ModuleNotFoundError: No module named 'src.tools.tavily'`

- [ ] **Step 3: Write minimal tavily.py implementation**

```python
# src/tools/tavily.py
"""Tavily deep search tool for LLM-optimized RAG."""

import json
import os
from datetime import datetime, timezone
from typing import Literal


def tavily_search(
    query: str,
    max_results: int = 10,
    time_range: Literal["d", "w", "m", "y", None] = None,
) -> str:
    """Execute Tavily deep search and return unified JSON Envelope.

    Tavily provides longer summaries (500 chars) optimized for RAG,
    reducing the need for additional web_fetch calls.

    Args:
        query: Search query
        max_results: Number of results (default 10)
        time_range: Time filter - 'd'=day, 'w'=week, 'm'=month, 'y'=year

    Returns:
        JSON Envelope string with search results
    """
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        return json.dumps({
            "source": "tavily",
            "error": "TAVILY_API_KEY not set",
            "results": [],
        })

    try:
        import httpx

        response = httpx.post(
            "https://api.tavily.com/search",
            json={
                "api_key": api_key,
                "query": query,
                "search_depth": "advanced",
                "max_results": max_results,
                "time_range": time_range,
                "include_answer": True,
                "include_raw_content": False,
            },
            timeout=30.0,
        )
        data = response.json()

        return json.dumps({
            "source": "tavily",
            "retrieved_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "query_used": query,
            "time_range_applied": time_range,
            "answer": data.get("answer"),
            "results": [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "published_at": r.get("published_date"),
                    "body": r.get("content", "")[:500],  # Tavily provides longer snippets
                }
                for r in data.get("results", [])[:max_results]
            ],
        }, ensure_ascii=False)

    except Exception as e:
        return json.dumps({
            "source": "tavily",
            "error": str(e),
            "results": [],
        })


TAVILY_TOOL = {
    "name": "tavily",
    "description": "Deep web search optimized for LLM RAG. Use for analysis, comprehensive reports, multi-source news, and trend research. Returns longer summaries (500 chars) to reduce web_fetch calls.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query in English"},
            "max_results": {"type": "integer", "default": 10},
            "time_range": {"type": "string", "enum": ["d", "w", "m", "y"], "description": "Time filter"},
        },
        "required": ["query"],
    },
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src pytest tests/tools/test_tavily.py::test_tavily_search_returns_unified_envelope -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tools/tavily.py tests/tools/test_tavily.py
git commit -m "feat: add Tavily deep search tool"
```

---

## Chunk 2: SearXNG Transparent Fallback

**Files:**
- Create: `src/tools/searxng.py`
- Create: `tests/tools/test_searxng.py`

- [ ] **Step 1: Write failing test for searxng_search**

```python
# tests/tools/test_searxng.py
import pytest
from unittest.mock import patch, MagicMock

def test_searxng_returns_unified_envelope():
    """SearXNG should return JSON Envelope with source='searxng'."""
    with patch("httpx.get") as mock_get:
        mock_get.return_value = MagicMock(
            json=lambda: {
                "results": [
                    {"title": "Test", "url": "https://test.com", "content": "Test content", "publishedDate": "2026-03-20"}
                ]
            }
        )
        from src.tools.searxng import searxng_search
        result = searxng_search("test query")
        import json
        data = json.loads(result)
        assert data["source"] == "searxng"
        assert data["query_used"] == "test query"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/tools/test_searxng.py::test_searxng_returns_unified_envelope -v`
Expected: `ERROR - ModuleNotFoundError: No module named 'src.tools.searxng'`

- [ ] **Step 3: Write minimal searxng.py implementation**

```python
# src/tools/searxng.py
"""SearXNG transparent fallback search (LLM不可见).

This module provides a fallback search when ddgs fails.
It is NOT exposed to the LLM router - used transparently in try-except.
"""

import json
import os
from datetime import datetime, timezone
from typing import Literal


def searxng_search(
    query: str,
    time_range: Literal["d", "w", "m", "y", None] = None,
) -> str:
    """Execute SearXNG search and return unified JSON Envelope.

    SearXNG aggregates multiple search engines (Google, Bing, DuckDuckGo).
    Used transparently when ddgs fails - LLM is unaware of this fallback.

    Args:
        query: Search query
        time_range: Time filter - 'd'=day, 'w'=week, 'm'=month, 'y'=year

    Returns:
        JSON Envelope string with search results
    """
    searxng_url = os.environ.get("SEARXNG_URL", "https://search.example.com")

    try:
        import httpx

        response = httpx.get(
            f"{searxng_url}/search",
            params={
                "q": query,
                "format": "json",
                "engines": "google,bing,duckduckgo",
                "time_range": time_range,
            },
            timeout=10.0,
        )
        results = response.json()

        return json.dumps({
            "source": "searxng",
            "retrieved_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "query_used": query,
            "time_range_applied": time_range,
            "results": [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "published_at": r.get("publishedDate"),
                    "body": r.get("content", "")[:300],
                }
                for r in results.get("results", [])[:5]
            ],
        }, ensure_ascii=False)

    except Exception as e:
        return json.dumps({
            "source": "searxng",
            "retrieved_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "query_used": query,
            "error": str(e),
            "results": [],
        })
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src pytest tests/tools/test_searxng.py::test_searxng_returns_unified_envelope -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tools/searxng.py tests/tools/test_searxng.py
git commit -m "feat: add SearXNG transparent fallback"
```

---

## Chunk 3: Tier Detection Logic

**Files:**
- Create: `src/tools/tier_detection.py`
- Create: `tests/tools/test_tier_detection.py`

- [ ] **Step 1: Write failing tests for tier detection**

```python
# tests/tools/test_tier_detection.py
import pytest
from src.tools.tier_detection import detect_search_tier, is_direct_url

def test_simple_query_detects_ddgs():
    """fact-check query should route to ddgs."""
    assert detect_search_tier("Is Apple a good stock?") == "ddgs"
    assert detect_search_tier("What is Apple's stock ticker?") == "ddgs"
    assert detect_search_tier("Apple official website") == "ddgs"

def test_deep_search_detects_tavily():
    """Analysis query should route to tavily."""
    assert detect_search_tier("Apple Q1 2026 earnings analysis") == "tavily"
    assert detect_search_tier("Latest news about Tesla") == "tavily"
    assert detect_search_tier("NVDA vs AMD comparison") == "tavily"

def test_url_detection():
    """URL input should be detected."""
    assert is_direct_url("https://seekingalpha.com/article/123") == True
    assert is_direct_url("http://reuters.com/news") == True
    assert is_direct_url("Apple stock analysis") == False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=src pytest tests/tools/test_tier_detection.py -v`
Expected: `ERROR - ModuleNotFoundError: No module named 'src.tools.tier_detection'`

- [ ] **Step 3: Write tier_detection.py implementation**

```python
# src/tools/tier_detection.py
"""Tier detection logic for search tool routing (低成本规则引擎).

Determines whether a query should use:
- ddgs: Simple fact queries, stock tickers, official websites
- tavily: Deep analysis, multi-source news, trend research
- None: Let LLM router decide (ambiguous cases)
"""

from typing import Literal

# 深度搜索关键词（触发 Tavily）
_DEEP_SEARCH_KEYWORDS = {
    # 分析/总结类
    "分析", "分析报告", "总结", "趋势",
    "analysis", "analyze", "summary", "trend",
    # 新闻类
    "新闻", "latest", "recent", "recently", "new",
    # 多源/全面类
    "multi-source", "comprehensive", "多源", "全面", "深度",
    "multi source", "all about",
    # 财报/业绩类
    "earnings", "财报", "业绩", "forecast", "outlook",
    "quarterly", "annual", "revenue", "profit",
    # 对比类
    "vs", "versus", "compare", "对比", "比较",
    # 预测/展望类
    "预测", "展望", "outlook", "projection", "outlook",
}

# 简单查询关键词（触发 ddgs）
_SIMPLE_QUERY_KEYWORDS = {
    # 股票代码类
    "股票代码", "stock ticker", "ticker", "股票号",
    # 官方网站类
    "官方网站", "official website", "官网", "homepage",
    # 事实核查类
    "fact-check", "验证", "是不是", "是否", "真伪",
    "is it true", "verify", "true or false",
    # 快速定义类
    "什么是", "what is", "who is", "定义",
    # 当前价格类
    "当前价格", "now price", "current price",
}

# 金融实体 + 多源组合 → tavily
_FINANCIAL_ENTITY_MULTI = {
    "stock", "stocks", "share", "shares", "equity", "equities",
    "bond", "bonds", "etf", "index",
}


def detect_search_tier(query: str) -> Literal["ddgs", "tavily", None]:
    """Detect which search tier a query should use.

    Returns:
        "ddgs" — Simple query pattern matched
        "tavily" — Deep search pattern matched
        None — Ambiguous, let LLM decide
    """
    query_lower = query.lower()

    # 检查简单查询关键词
    if any(kw in query_lower for kw in _SIMPLE_QUERY_KEYWORDS):
        return "ddgs"

    # 检查深度搜索关键词
    if any(kw in query_lower for kw in _DEEP_SEARCH_KEYWORDS):
        return "tavily"

    # 金融实体 + 多源需求 → tavily
    has_financial_entity = any(ent in query_lower for ent in _FINANCIAL_ENTITY_MULTI)
    has_multi_marker = any(kw in query_lower for kw in {"compare", "对比", "multiple", "多", "all"})
    if has_financial_entity and has_multi_marker:
        return "tavily"

    # 默认让 LLM 决定
    return None


def is_direct_url(text: str) -> bool:
    """Detect if input is a direct URL."""
    import re
    return bool(re.match(r"^https?://", text.strip()))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=src pytest tests/tools/test_tier_detection.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tools/tier_detection.py tests/tools/test_tier_detection.py
git commit -m "feat: add tier detection logic for search routing"
```

---

## Chunk 4: Update router.py with Tiered Routing

**Files:**
- Modify: `src/tools/router.py`
- Create: `tests/tools/test_router.py`

- [ ] **Step 1: Write failing tests for router tier integration**

```python
# tests/tools/test_router.py
import pytest
from unittest.mock import patch, MagicMock
from src.tools.router import ToolRouter, ToolChoice

def test_router_routes_simple_query_to_ddgs_without_llm():
    """Simple query should route to ddgs without LLM call."""
    with patch("src.tools.router.SGLangClient") as mock_llm:
        router = ToolRouter(llm_client=mock_llm)
        choice = router.select_tool("What is Apple's stock ticker?")
        assert choice.tool == "ddgs"
        assert choice.thought == "Rule-based: simple query detected → ddgs"
        # LLM should NOT be called
        mock_llm.return_value.client.chat.completions.parse.assert_not_called()

def test_router_routes_deep_search_to_tavily_without_llm():
    """Deep search query should route to tavily without LLM call."""
    with patch("src.tools.router.SGLangClient") as mock_llm:
        router = ToolRouter(llm_client=mock_llm)
        choice = router.select_tool("Apple Q1 2026 earnings analysis")
        assert choice.tool == "tavily"
        assert choice.thought == "Rule-based: deep search detected → tavily"
        mock_llm.return_value.client.chat.completions.parse.assert_not_called()

def test_router_routes_url_to_web_fetch():
    """URL input should route to web_fetch."""
    with patch("src.tools.router.SGLangClient") as mock_llm:
        router = ToolRouter(llm_client=mock_llm)
        choice = router.select_tool("https://seekingalpha.com/article/123")
        assert choice.tool == "web_fetch"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=src pytest tests/tools/test_router.py -v`
Expected: FAIL (router.py not yet updated)

- [ ] **Step 3: Update router.py with tiered routing**

Key changes to `router.py`:

1. Add imports:
```python
from src.tools.tier_detection import detect_search_tier, is_direct_url
from src.tools.tavily import tavily_search
from src.tools.searxng import searxng_search
```

2. Update `ToolChoice.tool` field:
```python
tool: Literal["ddgs", "tavily", "web_fetch", "browser", "finish"] = Field(...)
```

3. Replace `select_tool()` method:
```python
def select_tool(self, goal: str) -> ToolChoice | None:
    """Select appropriate tool using tier detection + LLM fallback."""
    # 1. URL detection
    if is_direct_url(goal):
        return ToolChoice(
            thought="Direct URL detected → web_fetch",
            tool="web_fetch",
            url=goal,
            reason="Direct URL input",
        )

    # 2. Rule-based tier detection
    tier = detect_search_tier(goal)

    if tier == "ddgs":
        return ToolChoice(
            thought=f"Rule-based: simple query detected → ddgs",
            tool="ddgs",
            query=goal,
            reason="Simple query pattern matched",
        )

    if tier == "tavily":
        return ToolChoice(
            thought=f"Rule-based: deep search detected → tavily",
            tool="tavily",
            query=goal,
            reason="Deep search keyword detected",
        )

    # 3. Ambiguous → LLM router
    try:
        completion = self.llm_client.client.chat.completions.parse(
            model="Qwen/Qwen3.5-35B-A3B",
            messages=[
                {"role": "system", "content": "You are a tool selection assistant. Respond with ONLY valid JSON."},
                {"role": "user", "content": self._build_router_prompt(goal, self.search_history)},
            ],
            response_format=ToolChoice,
        )
        return completion.choices[0].message.parsed
    except Exception as e:
        print(f"Error in tool selection: {e}")
        return ToolChoice(
            thought="Fallback: LLM error → ddgs",
            tool="ddgs",
            query=goal,
            reason="LLM selection failed, using safe fallback",
        )
```

4. Update `_build_router_prompt()` to include tavily:
```python
# Replace the tool descriptions in the prompt:
"""
┌─────────────────────────────────────────────────────────────┐
│ 1. ddgs (DuckDuckGo) — 简单查询                             │
│    - 事实核查 (fact-check)                                  │
│    - 股票代码查询                                           │
│    - 官方网站查找                                           │
│    - 快速单一答案查询                                        │
│                                                             │
│ 2. tavily — 深度搜索                                        │
│    - 需要分析、综合多篇来源                                   │
│    - 包含"分析"、"总结"、"趋势"等词                          │
│    - 最新新闻、财报、业绩报道                                 │
│    - "最近 X 怎么样", "X 的前景", "X vs Y"                  │
│    - Returns longer snippets (500 chars)                     │
│                                                             │
│ 3. web_fetch — URL 提取                                     │
│ 4. browser — 复杂交互                                       │
│ 5. finish — 完成                                            │
└─────────────────────────────────────────────────────────────┘
"""
```

5. Add `execute_ddgs()` method with try-except → SearXNG fallback:
```python
def execute_ddgs(self, query: str, time_range: Literal["d", "w", "m", "y", None] = None) -> str:
    """Execute ddgs search with transparent SearXNG fallback."""
    print(f"[Search] Using ddgs for: {query}")
    try:
        result = web_search(query, max_results=5, time_range=time_range)
    except Exception as e:
        print(f"[Search] ddgs failed ({e}), trying SearXNG...")
        result = searxng_search(query, time_range)

    self.search_history.append({
        "tool": "ddgs",
        "query": query,
        "result": result[:500],
    })
    return result

def execute_tavily(self, query: str, time_range: Literal["d", "w", "m", "y", None] = None) -> str:
    """Execute tavily deep search."""
    print(f"[Search] Using tavily for: {query}")
    result = tavily_search(query, time_range=time_range)

    self.search_history.append({
        "tool": "tavily",
        "query": query,
        "result": result[:500],
    })
    return result
```

6. Update `execute_web_search()` to use tier detection:
```python
def execute_web_search(self, query: str, time_range: Literal["d", "w", "m", "y", None] = None) -> str:
    """Execute search based on tier detection."""
    tier = detect_search_tier(query)

    if tier == "tavily":
        return self.execute_tavily(query, time_range)
    else:
        return self.execute_ddgs(query, time_range)
```

7. Update `run()` method to handle new "ddgs" tool:
```python
# In the run() method, replace:
# if choice.tool == "web_search" → if choice.tool in ("web_search", "ddgs")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=src pytest tests/tools/test_router.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tools/router.py tests/tools/test_router.py
git commit -m "feat: add tiered routing with ddgs/tavily/searxng"
```

---

## Chunk 5: Integration Test & README Update

**Files:**
- Modify: `README.md`
- Create: `tests/tools/test_integration.py`

- [ ] **Step 1: Write integration test for full routing flow**

```python
# tests/tools/test_integration.py
"""Integration tests for tiered routing flow."""
import pytest
from unittest.mock import patch, MagicMock

def test_full_flow_ddgs_fallback_to_searxng():
    """ddgs failure should trigger SearXNG transparently."""
    from src.tools.router import ToolRouter

    router = ToolRouter()

    # First call fails, second (searxng) succeeds
    with patch("src.tools.web_search.web_search") as mock_ddgs, \
         patch("src.tools.searxng.searxng_search") as mock_searxng:
        mock_ddgs.side_effect = Exception("Rate limit")
        mock_searxng.return_value = '{"source": "searxng", "results": []}'

        result = router.execute_ddgs("test query")
        mock_searxng.assert_called_once()
```

- [ ] **Step 2: Run integration test**

Run: `PYTHONPATH=src pytest tests/tools/test_integration.py -v`

- [ ] **Step 3: Update README.md Web Tools section**

Add Tavily/SearXNG to the README:

```markdown
### Web Tools

多工具 Agent 系统，支持智能路由：

- **ddgs** (DuckDuckGo) — 简单查询：fact-check、股票代码、官方网站
- **tavily** — 深度搜索：分析报告、多源新闻、趋势研究（RAG 优化，500 chars 摘要）
- **web_fetch** — URL 内容提取
- **searxng** — ddgs 失败时的透明容错（LLM 不可见）

**Tiered Routing**:
- 关键词规则引擎优先检测，简单/深度查询直接路由，不调 LLM
- 模糊情况 → LLM 路由判断

```python
from src.tools.router import ToolRouter

router = ToolRouter()
# Routes to: ddgs, tavily, web_fetch, browser, or finish
```
```

- [ ] **Step 4: Run all tests**

Run: `PYTHONPATH=src pytest tests/tools/ -v`

- [ ] **Step 5: Commit README update**

```bash
git add README.md
git commit -m "docs: update README with tiered routing web tools"
```

---

## Summary

| Chunk | Tasks | Files |
|-------|-------|-------|
| 1 | Tavily search tool | `src/tools/tavily.py`, `tests/tools/test_tavily.py` |
| 2 | SearXNG transparent fallback | `src/tools/searxng.py`, `tests/tools/test_searxng.py` |
| 3 | Tier detection logic | `src/tools/tier_detection.py`, `tests/tools/test_tier_detection.py` |
| 4 | Update router with tiered routing | `src/tools/router.py`, `tests/tools/test_router.py` |
| 5 | Integration test + README | `tests/tools/test_integration.py`, `README.md` |

**Total: 5 chunks, ~25 steps**

---

## Prerequisites

Before running tests, install dependencies:
```bash
uv add httpx
uv add tavily-python  # if available, or use httpx directly
```
