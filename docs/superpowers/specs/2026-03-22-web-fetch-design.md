# Web Fetch Tool Design

## Overview

Implement a lightweight web content fetching tool (`web_fetch`) that complements the existing `web_search` (DDGS) tool. The tool fetches URL content for RAG workflows, returns metadata-enriched Markdown, and gracefully degrades when encountering dynamic or protected pages.

## Architecture

### Tool Positioning

| Tool | Engine | Use Case | Priority |
|------|--------|----------|----------|
| `web_search` | DDGS API | Quick factual queries, news, search | Primary (query-based) |
| `web_fetch` | scrapling | Fetching specific URL content for RAG | Primary (URL-based) |
| `MarketExplorer` | agent-browser + scrapling | JS-rendered pages, anti-bot sites | Fallback (Agent-decided) |

### Data Flow

```
Agent calls web_fetch(url)
    │
    ├─► Internal blacklist check (_is_blacklisted_domain)
    │       │
    │       ├─► Blacklisted → return failure (BLACKLISTED_DOMAIN)
    │       │
    │       └─► Normal URL → proceed
    │
    └─► scrapling HTTP fetch + HTML→Markdown
            │
            ├─► Success → return {url, title, description, content: Markdown}
            │
            └─► Failure → return {url, status: "failed", error_code, error_message, suggestion}

Agent reads suggestion → decides whether to call MarketExplorer as separate tool
```

**Note:** web_fetch and MarketExplorer are separate tools. web_fetch returns a structured failure response; the Agent decides whether to invoke MarketExplorer based on the `suggestion` field. There is no internal handoff between tools.

**MarketExplorer Tool Schema (for reference):**
- Name: `market_explorer`
- See: `docs/superpowers/specs/2026-03-19-browser-exploration-design.md`

### Processing Order (Critical)

1. **First:** Extract metadata (title, description) from raw HTML
2. **Then:** Clean HTML (remove scripts, styles, nav, footer, etc.)
3. **Finally:** Convert cleaned HTML to Markdown

This ordering ensures metadata extraction is not affected by content cleaning.

### scrapling Dual Role

| Context | scrapling Responsibility |
|---------|-------------------------|
| `web_fetch` | Direct HTTP fetch + HTML→Markdown conversion |
| `MarketExplorer` | Parse agent-browser DOM snapshot → HTML→Markdown (documented in MarketExplorer design) |

## Functionality

### Core Features

1. **Fast URL Content Fetching**
   - Async HTTP GET via `httpx.AsyncClient` (scrapling's underlying HTTP client)
   - Default headers: `User-Agent: Mozilla/5.0`, `Accept-Language: en-US`
   - **HTML→Markdown: Use `trafilatura.extract()`** with `output_format="markdown", include_links=True`
   - trafilatura handles both boilerplate removal AND Markdown conversion in one step
   - Target latency: < 3 seconds end-to-end (measured from call to response)
   - **async def** - enables concurrent tool calls in async Agent frameworks

2. **Metadata-Enriched Output**
   - Extract `<title>` tag content (before any HTML cleaning)
   - Extract `<meta name="description">` content (before any HTML cleaning)
   - Zero-cost extraction without LLM

3. **Content Cleaning**
   - Remove `<script>`, `<style>`, `<nav>`, `<footer>`, `<header>`, `<aside>` elements
   - Remove advertising blocks, cookie banners, comment elements
   - Preserve main content structure (headings, lists, tables, paragraphs)
   - Convert to Markdown format

4. **Smart Error Reporting**
   - Catch all exceptions, never crash Agent
   - Return structured error with `error_code`, `error_message`, `suggestion`
   - Let Agent decide fallback strategy

5. **Domain Heuristic Routing**
   - Check URL against known dynamic domain blacklist (internal helper)
   - Return immediate failure for blacklisted domains (avoid wasted fetch attempt)

### Output Schema

**Success:**
```json
{
  "url": "https://example.com/article",
  "title": "Page Title",
  "description": "Meta description text",
  "content": "## Article Heading\n\nParagraph text here...\n\n- List item 1\n- List item 2\n\n| Column 1 | Column 2 |\n|----------|----------|\n| Cell 1   | Cell 2   |"
}
```

**Failure:**
```json
{
  "url": "https://example.com/data",
  "status": "failed",
  "error_code": "403_FORBIDDEN",
  "error_message": "Access denied. This site may have anti-bot protection (Cloudflare, etc.).",
  "suggestion": "Try using MarketExplorer (real browser) to access this URL.",
  "content": ""
}
```

### Error Codes

| Code | Meaning | Suggestion |
|------|---------|------------|
| `404_NOT_FOUND` | Page doesn't exist (HTTP 404) | Try searching for alternative sources |
| `403_FORBIDDEN` | Access denied (HTTP 403) | Use MarketExplorer with real browser |
| `TIMEOUT` | Request exceeded 10 second timeout | The site may be slow; try again later |
| `CONNECTION_ERROR` | Network failure (DNS, refused connection) | Check your connection |
| `INVALID_URL` | Malformed URL | Verify the URL is correct |
| `BLACKLISTED_DOMAIN` | Known dynamic site (in blacklist) | Use MarketExplorer directly |
| `PARSE_ERROR` | HTML parsing failed | Use MarketExplorer for complex pages |
| `UNKNOWN` | Unexpected error | Report this issue |

### Domain Blacklist (Initial Set)

Maintained in `src/tools/web_fetch.py` as a private constant:

```python
_KNOWN_DYNAMIC_DOMAINS = [
    "twitter.com",
    "x.com",
    "tradingview.com",
    "app.uniswap.org",
    "coinbase.com",
    "bloomberg.com",
    "wsj.com",
]
```

**Matching Algorithm:** Domain extraction + suffix match. Extract the domain from the URL, then check if it equals the blacklisted domain OR ends with `.` + blacklisted domain.

| Extracted Domain | Matches? |
|-----------------|----------|
| `tradingview.com` | ✅ (equals `tradingview.com`) |
| `blog.tradingview.com` | ✅ (ends with `.tradingview.com`) |
| `nottradingview.com` | ❌ (does NOT end with `.tradingview.com`) |

**Extensibility:** Add new domains as needed. This is a static list for v1.

### Content Size Limits

- **Max content size:** 100KB of Markdown text
- **Truncation:** If content exceeds limit, scan backward for `\n\n` (paragraph boundary), truncate there, append `...(truncated)`
- **Title/description:** No limit, but typically < 200 chars

## Implementation

### Files to Create/Modify

| File | Action | Purpose |
|------|--------|---------|
| `src/tools/web_fetch.py` | Create | Main web_fetch tool |

**Removed from scope:** `src/tools/heuristic_router.py` - Domain checking is handled internally by `_is_blacklisted_domain()` helper within web_fetch.py.

**Removed from scope:** `src/browser/explorer.py` modification. scrapling integration in MarketExplorer is already covered by existing design.

### Dependencies

- `httpx>=0.27.0` (async HTTP client, already used by scrapling)
- `trafilatura>=1.0.0` (HTML→Markdown + boilerplate removal, add to pyproject.toml)
- `beautifulsoup4>=4.12.0` (metadata extraction from raw HTML, already in pyproject.toml)
- `lxml>=6.0.2` (HTML parser for BeautifulSoup, already in pyproject.toml)

### API Design

```python
# src/tools/web_fetch.py

from dataclasses import dataclass
import json
import httpx
import trafilatura

@dataclass
class WebFetchResult:
    url: str
    title: str | None = None
    description: str | None = None
    content: str = ""
    status: Literal["success", "failed"] = "success"
    error_code: str | None = None
    error_message: str | None = None
    suggestion: str | None = None

def _is_blacklisted_domain(url: str) *********REMOVED********* bool:
    """Internal helper. Returns True if URL domain equals or ends with . + known dynamic domain."""
    ...

def _extract_metadata(html: str) *********REMOVED********* tuple[str | None, str | None]:
    """Extract title and description from raw HTML using BeautifulSoup. Returns (title, description)."""
    ...

def _truncate_content(content: str, max_size: int = 100_000) *********REMOVED********* str:
    """Truncate content at last paragraph boundary if > max_size."""
    ...

async def web_fetch(url: str) *********REMOVED********* WebFetchResult:
    """Fetch URL content and return metadata + Markdown (async for concurrent tool calls)."""
    # 1. Check blacklist
    # 2. Fetch via httpx.AsyncClient (timeout=10s)
    # 3. Extract metadata from raw HTML (BeautifulSoup)
    # 4. Use trafilatura.extract(html, output_format="markdown", include_links=True) for content
    # 5. Truncate if needed
    # 6. Return result as dict (dataclasses.asdict) for JSON serialization
    ...

def web_fetch_sync(url: str) *********REMOVED********* WebFetchResult:
    """Synchronous wrapper for non-async contexts."""
    return asyncio.run(web_fetch(url))

def serialize_result(result: WebFetchResult) *********REMOVED********* str:
    """Serialize result to JSON string for LLM tool call response."""
    return json.dumps(dataclasses.asdict(result))

# Tool definition for LLM tool calling
WEB_FETCH_TOOL = {
    "name": "web_fetch",
    "description": "Fetch URL content for RAG. Returns metadata + Markdown. Use for static pages. For JS-heavy sites, expect failure and use MarketExplorer instead.",
    "input_schema": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
}
```

## Testing

### Unit Tests

| Test Case | Description |
|-----------|-------------|
| `test_extract_title` | Given HTML with `<title>Test</title>`, verify `result.title == "Test"` |
| `test_extract_description` | Given HTML with `<meta name="description" content="Desc">`, verify `result.description == "Desc"` |
| `test_content_cleaning_removes_scripts` | Given HTML with `<script>alert(1)</script>`, verify content has no script |
| `test_content_cleaning_preserves_headings` | Given HTML with `<h1>Heading</h1>`, verify content contains `## Heading` |
| `test_content_truncation` | Given large HTML producing >100KB Markdown, verify truncation ends at paragraph boundary |
| `test_truncation_algorithm` | Verify truncation scans backward for `\n\n` |
| `test_error_404` | Given HTTP 404 response, verify `error_code == "404_NOT_FOUND"` |
| `test_error_timeout` | Given slow server, verify timeout after 10s with `TIMEOUT` code |
| `test_error_parse_error` | Given malformed HTML, verify `error_code == "PARSE_ERROR"` |
| `test_blacklisted_domain` | Given URL `https://tradingview.com/...`, verify `error_code == "BLACKLISTED_DOMAIN"` |
| `test_blacklist_exact_match` | Given URL `https://nottradingview.com`, verify NO blacklist match (false positive prevention) |
| `test_blacklist_subdomain` | Given URL `https://blog.twitter.com`, verify blacklist match |

### Integration Tests

| Test Case | Description |
|-----------|-------------|
| `test_fetch_static_wikipedia` | Fetch Wikipedia article, verify `status="success"`, content is non-empty Markdown |
| `test_fetch_news_site` | Fetch news article, verify Markdown has headings, lists |
| `test_fetch_reuters` | Fetch Reuters article, verify `title` and `description` extracted |
| `test_agent_decides_market_explorer` | Given blacklisted URL, verify `error_code="BLACKLISTED_DOMAIN"` and `suggestion` field present |

## Notes

- `web_fetch` is **async def** (enables concurrent tool calls in async Agent frameworks)
- `web_fetch_sync()` wrapper provided for non-async contexts
- `web_fetch` never raises exceptions to Agent (all errors returned as JSON)
- Result must be serialized via `dataclasses.asdict(result)` + `json.dumps()` for LLM compatibility
- Agent (LLM) decides fallback based on `suggestion` field
- Timeout is fixed at 10 seconds (httpx timeout)
- Metadata extraction happens before trafilatura processing
- trafilatura handles boilerplate removal AND Markdown conversion in one step
