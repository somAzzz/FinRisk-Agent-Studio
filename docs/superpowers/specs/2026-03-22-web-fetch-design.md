# Web Fetch Tool Design

## Overview

Implement a lightweight web content fetching tool (`web_fetch`) that complements the existing `web_search` (DDGS) tool. The tool fetches URL content for RAG workflows, returns metadata-enriched Markdown, and gracefully degrades when encountering dynamic or protected pages.

## Architecture

### Tool Positioning

| Tool | Engine | Use Case | Priority |
|------|--------|----------|----------|
| `web_search` | DDGS API | Quick factual queries, news, search | Primary (query-based) |
| `web_fetch` | scrapling | Fetching specific URL content for RAG | Primary (URL-based) |
| `MarketExplorer` | agent-browser + scrapling | JS-rendered pages, anti-bot sites | Fallback |

### Data Flow

```
Agent calls web_fetch(url)
    │
    ├─► ToolRouter heuristic check (domain whitelist/blacklist)
    │       │
    │       ├─► Blacklisted domain → redirect to MarketExplorer
    │       │
    │       └─► Normal URL → proceed
    │
    └─► scrapling HTTP fetch + parse
            │
            ├─► Success → return {url, title, description, content: Markdown}
            │
            └─► Failure → return {url, status: "failed", error_code, error_message, suggestion}
```

### scrapling Dual Role

| Context | scrapling Responsibility |
|---------|-------------------------|
| `web_fetch` | Direct HTTP fetch + HTML→Markdown conversion |
| `MarketExplorer` | Parse agent-browser DOM snapshot + HTML→Markdown |

## Functionality

### Core Features

1. **Fast URL Content Fetching**
   - HTTP GET via scrapling's auto-stealth mode
   - Parse HTML to metadata + Markdown
   - Target latency: < 2 seconds

2. **Metadata-Enriched Output**
   - Extract `<title>`, `<meta description>`
   - Return zero-cost metadata without LLM

3. **Smart Error Reporting**
   - Catch all exceptions, never crash Agent
   - Return structured error with `error_code`, `error_message`, `suggestion`
   - Let Agent decide fallback strategy

4. **Domain Heuristic Routing**
   - Maintain lightweight domain blacklist for known JS-heavy sites
   - Auto-route to MarketExplorer for blacklisted domains

### Output Schema

**Success:**
```json
{
  "url": "https://example.com/article",
  "title": "Page Title",
  "description": "Meta description text",
  "content": "## Cleaned Markdown Content\n\n..."
}
```

**Failure:**
```json
{
  "url": "https://example.com/data",
  "status": "failed",
  "error_code": "403_FORBIDDEN",
  "error_message": "Access denied. This site may have anti-bot protection.",
  "suggestion": "Try using MarketExplorer (real browser) to access this URL.",
  "content": ""
}
```

### Error Codes

| Code | Meaning | Suggestion |
|------|---------|------------|
| `404_NOT_FOUND` | Page doesn't exist | Try searching for alternative sources |
| `TIMEOUT` | Request timed out | The site may be slow; try again later |
| `403_FORBIDDEN` | Access denied | Use MarketExplorer with real browser |
| `CONNECTION_ERROR` | Network failure | Check your connection |
| `INVALID_URL` | Malformed URL | Verify the URL is correct |
| `PARSE_ERROR` | HTML parsing failed | Use MarketExplorer for complex pages |
| `UNKNOWN` | Unexpected error | Report this issue |

### Domain Blacklist (Initial Set)

```python
KNOWN_DYNAMIC_DOMAINS = [
    "twitter.com",
    "x.com",
    "tradingview.com",
    "app.uniswap.org",
    "coinbase.com",
    "bloomberg.com",
    "wsj.com",
]
```

## Implementation

### Files to Create/Modify

| File | Action | Purpose |
|------|--------|---------|
| `src/tools/web_fetch.py` | Create | Main web_fetch tool |
| `src/tools/router.py` | Modify | Add heuristic routing |
| `src/browser/explorer.py` | Modify | Use scrapling for DOM parsing |

### Dependencies

- `scrapling>=0.4.2` (already in pyproject.toml)
- `agent-browser` CLI (already used)

## Testing

1. **Unit tests** for scrapling parsing
2. **Integration tests** for success/failure paths
3. **Domain routing tests** for blacklist matching

## Notes

- `web_fetch` is synchronous (fast, no async needed)
- `web_fetch` never raises exceptions to Agent
- LLM decides fallback based on error response
