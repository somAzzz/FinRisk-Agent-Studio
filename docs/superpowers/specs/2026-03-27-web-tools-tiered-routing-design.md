# Web Tools Tiered Routing Design

**Date**: 2026-03-27
**Status**: Implemented (commits `d806528` / `150d374` / `7361062` / `4d8c0de` / `d9caeca`). Architecture has since evolved into `src/tools/search_router.py` + `src/tools/providers/` (duckduckgo, brave, tavily, exa, serper, serpapi, searxng) + `src/tools/search_cache.py`. Kept as the historical design rationale for the tier-based routing decision. For the current state see `src/tools/search_router.py` and `README.md` § Browser Exploration.
**Type**: Implementation Design

## Overview

Add Tavily and SearXNG to the web tools system while maintaining DuckDuckGo as the free fallback. Implements a tiered routing strategy to optimize for RAG quality, latency, and cost.

## Goals

1. **Improve RAG quality** for financial analysis by using Tavily's long summaries
2. **Reduce latency** by minimizing unnecessary `web_fetch` calls
3. **Increase recall** via multi-source aggregation for financial entity queries
4. **Maintain privacy/compliance** through SearXNG self-hosted option
5. **Preserve cost efficiency** by reserving Tavily for deep search only

## Architecture

### Tiered Routing (3-Tier + 1 Backup)

```
┌─────────────────────────────────────────────────────────────┐
│  Query Input                                                │
└─────────────────────┬───────────────────────────────────────┘
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  1. URL Detection                                           │
│     Input contains http/https → web_fetch (skip routing)    │
└─────────────────────┬───────────────────────────────────────┘
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  2. Rule-Based Tier Detection (低成本规则引擎)              │
│                                                             │
│     Simple Query → ddgs (DuckDuckGo)                        │
│     Deep Search → tavily                                    │
│     Uncertain → LLM Router                                  │
└─────────────────────┬───────────────────────────────────────┘
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  3. LLM Router (模糊情况)                                   │
│     Chooses: ddgs | tavily | web_fetch | browser | finish  │
└─────────────────────┬───────────────────────────────────────┘
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  4. Tool Execution                                         │
│     ddgs → try-except → SearXNG fallback (transparent)      │
│     tavily → direct                                        │
│     web_fetch → direct                                     │
└─────────────────────────────────────────────────────────────┘
```

### Tool Inventory

| Tool | Layer | Visibility | Purpose |
|------|-------|------------|---------|
| **ddgs** | Level 1 | LLM visible | 简单事实、股票代码、官方网站、fact-check |
| **tavily** | Level 2 | LLM visible | 深度分析、多源新闻、趋势研究、RAG |
| **web_fetch** | Level 3 | LLM visible | 直接 URL 内容提取 |
| **searxng** | Backup | **LLM 不可见** | ddgs 失败时的透明容错 |

### Tier Detection Keywords

**ddgs (Simple Query)**:
- 事实核查: `fact-check`, `验证`, `是不是`, `是否`
- 股票代码: `股票代码`, `stock ticker`, `ticker`
- 官方网站: `官方网站`, `official website`, `官网`
- 快速查询: `什么是`, `what is`, `who is`, `价格`, `price`

**tavily (Deep Search)**:
- 分析类: `分析`, `分析报告`, `总结`, `趋势`
- 新闻类: `新闻`, `latest`, `recent`, `recently`
- 多源类: `multi-source`, `comprehensive`, `多源`, `全面`, `深度`
- 财报类: `earnings`, `财报`, `业绩`, `forecast`, `outlook`
- 对比类: `X vs Y`, `compare`, `对比`

## Data Models

### Unified JSON Envelope

All search tools return consistent format:

```json
{
  "source": "ddgs|tavily|searxng",
  "retrieved_at": "2026-03-27T10:30:00Z",
  "query_used": "Apple Q1 2026 earnings analysis",
  "time_range_applied": "m",
  "answer": "...",        // tavily only
  "results": [
    {
      "title": "Apple Reports Q1 2026 Earnings",
      "url": "https://...",
      "published_at": "2026-03-15",
      "body": "..."       // ddgs: 300 chars, tavily: 500 chars
    }
  ]
}
```

### ToolChoice Model (Updated)

```python
class ToolChoice(BaseModel):
    tool: Literal["ddgs", "tavily", "web_fetch", "browser", "finish"]
    # ... other fields
```

## File Structure

```
src/tools/
├── router.py          # Updated: tiered routing logic
├── web_search.py       # Existing: ddgs implementation
├── web_fetch.py        # Existing: URL extraction
├── tavily.py          # NEW: Tavily API wrapper
└── searxng.py         # NEW: Transparent fallback (not LLM-visible)
```

## API Keys

| Service | Env Variable | Required |
|---------|--------------|----------|
| Tavily | `TAVILY_API_KEY` | Yes (for deep search) |
| SearXNG | `SEARXNG_URL` | No (uses public instance fallback) |

## Router Prompt Update

The LLM router prompt is updated to:

1. **3 visible tools**: ddgs, tavily, web_fetch
2. **Clear tier instructions**: Simple → ddgs, Deep → tavily
3. **SearXNG hidden**: LLM doesn't know about SearXNG; transparent fallback in code

## Implementation Notes

1. **Rule-based routing first**: Keywords detected → direct routing, no LLM call
2. **LLM only for ambiguous cases**: Reduces latency and cost
3. **SearXNG try-except wrapper**: ddgs call wrapped; on exception, silently try SearXNG
4. **Tavily returns longer snippets**: 500 chars vs ddgs 300 chars → fewer web_fetch calls needed

## Testing Checklist

- [ ] Simple query routes to ddgs without LLM call
- [ ] Deep search query routes to tavily without LLM call
- [ ] URL input routes directly to web_fetch
- [ ] Ambiguous query triggers LLM router
- [ ] ddgs failure triggers SearXNG fallback transparently
- [ ] All tools return unified JSON Envelope format
- [ ] Router prompt correctly guides LLM to choose ddgs vs tavily
