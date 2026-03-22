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
    ├─► HeuristicRouter domain check
    │       │
    │       ├─► Blacklisted domain → return failure with suggestion
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

### scrapling Dual Role

| Context | scrapling Responsibility |
|---------|-------------------------|
| `web_fetch` | Direct HTTP fetch + HTML→Markdown conversion |
| `MarketExplorer` | Parse agent-browser DOM snapshot → HTML→Markdown (already documented in MarketExplorer design) |

### HeuristicRouter (Domain-based Routing)

Located in `src/tools/heuristic_router.py` (new file). Performs URL-based routing without LLM:

- Checks URL against `KNOWN_DYNAMIC_DOMAINS` blacklist
- Returns routing decision immediately (no LLM call)
- Used as a pre-check before invoking web_fetch

## Functionality

### Core Features

1. **Fast URL Content Fetching**
   - HTTP GET via scrapling
   - HTML→Markdown conversion using scrapling's extractor
   - Target latency: < 3 seconds end-to-end (measured from call to response)

2. **Metadata-Enriched Output**
   - Extract `<title>` tag content
   - Extract `<meta name="description">` content
   - Zero-cost extraction without LLM

3. **Content Cleaning**
   - Remove `<script>`, `<style>`, `<nav>`, `<footer>`, `<header>` elements
   - Remove advertising blocks and cookie banners
   - Preserve main content structure (headings, lists, tables, paragraphs)
   - Convert to Markdown format

4. **Smart Error Reporting**
   - Catch all exceptions, never crash Agent
   - Return structured error with `error_code`, `error_message`, `suggestion`
   - Let Agent decide fallback strategy

5. **Domain Heuristic Routing**
   - Check URL against known dynamic domain blacklist
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

Maintained in `src/tools/heuristic_router.py`:

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

**Extensibility:** Add new domains as needed. This is a static list for v1.

### Content Size Limits

- **Max content size:** 100KB of Markdown text
- **Truncation:** If content exceeds limit, truncate at last complete paragraph and append `...(truncated)`
- **Title/description:** No limit, but typically < 200 chars

## Implementation

### Files to Create/Modify

| File | Action | Purpose |
|------|--------|---------|
| `src/tools/web_fetch.py` | Create | Main web_fetch tool |
| `src/tools/heuristic_router.py` | Create | Domain-based URL routing |
| `src/tools/router.py` | No change | Tool selection logic unchanged |

**Removed from scope:** `src/browser/explorer.py` modification. scrapling integration in MarketExplorer is already covered by existing design.

### Dependencies

- `scrapling>=0.4.2` (already in pyproject.toml)
- `agent-browser` CLI (already used)

### API Design

```python
# src/tools/web_fetch.py

class WebFetchResult(BaseModel):
    url: str
    title: str | None = None
    description: str | None = None
    content: str = ""
    status: Literal["success", "failed"] = "success"
    error_code: str | None = None
    error_message: str | None = None
    suggestion: str | None = None

def web_fetch(url: str) *********REMOVED********* WebFetchResult:
    """Fetch URL content and return metadata + Markdown."""
    ...

# Tool definition for LLM tool calling
WEB_FETCH_TOOL = {
    "name": "web_fetch",
    "description": "Fetch URL content for RAG. Returns metadata + Markdown. Use for static pages. For JS-heavy sites, expect failure and use MarketExplorer instead.",
    "input_schema": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
}
```

```python
# src/tools/heuristic_router.py

def should_use_market_explorer(url: str) *********REMOVED********* bool:
    """Returns True if URL matches known dynamic domain blacklist."""
    ...

def route_to_tool(url: str) *********REMOVED********* str:
    """Returns 'web_fetch' or 'market_explorer' based on heuristics."""
    ...
```

## Testing

### Unit Tests

| Test Case | Description |
|-----------|-------------|
| `test_extract_title` | Given HTML with `<title>Test</title>`, verify `result.title == "Test"` |
| `test_extract_description` | Given HTML with `<meta name="description" content="Desc">`, verify `result.description == "Desc"` |
| `test_content_cleaning_removes_scripts` | Given HTML with `<script>alert(1)</script>`, verify content has no script |
| `test_content_cleaning_preserves_headings` | Given HTML with `<h1>Heading</h1>`, verify content contains `## Heading` |
| `test_content_truncation` | Given large HTML producing >100KB Markdown, verify truncation |
| `test_error_404` | Given HTTP 404 response, verify `error_code == "404_NOT_FOUND"` |
| `test_error_timeout` | Given slow server, verify timeout after 10s with `TIMEOUT` code |
| `test_blacklisted_domain` | Given URL `https://tradingview.com/...`, verify `error_code == "BLACKLISTED_DOMAIN"` |

### Integration Tests

| Test Case | Description |
|-----------|-------------|
| `test_fetch_static_wikipedia` | Fetch Wikipedia article, verify success with content |
| `test_fetch_news_site` | Fetch news article, verify Markdown formatting |
| `test_agent_decides_market_explorer` | Given blacklisted URL, verify Agent can read suggestion and call MarketExplorer |

### HeuristicRouter Tests

| Test Case | Description |
|-----------|-------------|
| `test_blacklist_matching` | Verify `tradingview.com` matches `*tradingview.com*` pattern |
| `test_whitelist_normal_url` | Verify `example.com` does not match blacklist |
| `test_subdomain_handling` | Verify `blog.twitter.com` triggers blacklist |

## Notes

- `web_fetch` is synchronous
- `web_fetch` never raises exceptions to Agent (all errors returned as JSON)
- LLM/Agent decides fallback based on `suggestion` field
- Timeout is fixed at 10 seconds (configurable in future)
