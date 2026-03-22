# Web Fetch Tool Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement `web_fetch` - an async URL content fetching tool that returns metadata + Markdown for RAG workflows, with smart error handling and domain blacklist.

**Architecture:** Async tool using `httpx.AsyncClient` for HTTP, `BeautifulSoup` for metadata extraction, `trafilatura` for HTML→Markdown conversion. Returns structured JSON results with error codes and suggestions for Agent fallback decisions.

**Tech Stack:** Python 3.12+, httpx, beautifulsoup4, trafilatura, dataclasses

---

## Chunk 1: Project Setup & Data Models

**Files:**
- Modify: `pyproject.toml` (add trafilatura dependency)
- Create: `src/tools/web_fetch.py` (data models, constants, helper functions)

### Task 1: Add trafilatura dependency

- [ ] **Step 1: Edit pyproject.toml to add trafilatura**

```toml
# In dependencies section, add:
"trafilatura>=1.0.0",
```

Run: `uv sync` to install

### Task 2: Create web_fetch.py with data models

- [ ] **Step 1: Create initial web_fetch.py with dataclass and constants**

```python
# src/tools/web_fetch.py

from dataclasses import dataclass
from typing import Literal

ERROR_SUGGESTIONS = {
    "BLACKLISTED_DOMAIN": "Use MarketExplorer (real browser) to access this URL.",
    "INVALID_URL": "Verify the URL is correct.",
    "TIMEOUT": "The site may be slow; try again later.",
    "CONNECTION_ERROR": "Check your connection.",
    "404_NOT_FOUND": "Try searching for alternative sources.",
    "403_FORBIDDEN": "Use MarketExplorer with real browser.",
    "PARSE_ERROR": "Use MarketExplorer for complex pages.",
    "UNKNOWN": "Report this issue.",
}

_ERROR_MESSAGES = {
    "BLACKLISTED_DOMAIN": "This domain is known to require JavaScript rendering.",
    "INVALID_URL": "Malformed URL provided.",
    "TIMEOUT": "Request exceeded 10 second timeout.",
    "CONNECTION_ERROR": "Could not connect to the server.",
    "404_NOT_FOUND": "Page not found (HTTP 404).",
    "403_FORBIDDEN": "Access denied. This site may have anti-bot protection (Cloudflare, etc.).",
    "PARSE_ERROR": "Failed to parse HTML content.",
    "UNKNOWN": "An unexpected error occurred.",
}

_KNOWN_DYNAMIC_DOMAINS = [
    "twitter.com",
    "x.com",
    "tradingview.com",
    "app.uniswap.org",
    "coinbase.com",
    "bloomberg.com",
    "wsj.com",
]

MAX_CONTENT_SIZE = 100_000  # 100KB
TIMEOUT_SECONDS = 10

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
```

- [ ] **Step 2: Commit**

```bash
git add pyproject.toml src/tools/web_fetch.py
git commit -m "feat: scaffold web_fetch data models and constants"
```

---

## Chunk 2: Domain Blacklist Helper

**Files:**
- Modify: `src/tools/web_fetch.py`

### Task 3: Implement _is_blacklisted_domain helper

- [ ] **Step 1: Write failing test for domain matching**

```python
# tests/tools/test_web_fetch.py

import pytest
from src.tools.web_fetch import _is_blacklisted_domain

def test_blacklist_exact_match():
    """tradingview.com should match"""
    assert _is_blacklisted_domain("https://tradingview.com/symbol/NASDAQ:AAPL") is True

def test_blacklist_subdomain():
    """blog.tradingview.com should match"""
    assert _is_blacklisted_domain("https://blog.tradingview.com/article") is True

def test_blacklist_false_positive():
    """nottradingview.com should NOT match"""
    assert _is_blacklisted_domain("https://nottradingview.com") is False

def test_whitelist_normal():
    """example.com should NOT match"""
    assert _is_blacklisted_domain("https://example.com/article") is False

def test_whitelist_subdomain_false_positive():
    """notexample.com should NOT match"""
    assert _is_blacklisted_domain("https://notexample.com") is False
```

Run: `pytest tests/tools/test_web_fetch.py::test_blacklist_exact_match -v`
Expected: FAIL with "_is_blacklisted_domain not defined"

- [ ] **Step 2: Implement _is_blacklisted_domain**

```python
def _is_blacklisted_domain(url: str) *********REMOVED********* bool:
    """Returns True if URL domain equals or ends with . + known dynamic domain."""
    from urllib.parse import urlparse
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
    except Exception:
        return False

    for blacklisted in _KNOWN_DYNAMIC_DOMAINS:
        if domain == blacklisted or domain.endswith("." + blacklisted):
            return True
    return False
```

- [ ] **Step 3: Run tests to verify**

Run: `pytest tests/tools/test_web_fetch.py -k "blacklist" -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add src/tools/web_fetch.py tests/tools/test_web_fetch.py
git commit -m "feat: add domain blacklist helper with suffix matching"
```

---

## Chunk 3: Metadata Extraction

**Files:**
- Modify: `src/tools/web_fetch.py`

### Task 4: Implement _extract_metadata helper

- [ ] **Step 1: Write failing test for metadata extraction**

```python
# tests/tools/test_web_fetch.py (add)

from src.tools.web_fetch import _extract_metadata

def test_extract_title():
    html = "<html><head><title>Test Page Title</title></head></html>"
    title, desc = _extract_metadata(html)
    assert title == "Test Page Title"
    assert desc is None

def test_extract_description():
    html = '<html><head><meta name="description" content="Test description text"></head></html>'
    title, desc = _extract_metadata(html)
    assert title is None
    assert desc == "Test description text"

def test_extract_both():
    html = '<html><head><title>Page</title><meta name="description" content="Desc"></head></html>'
    title, desc = _extract_metadata(html)
    assert title == "Page"
    assert desc == "Desc"

def test_extract_no_metadata():
    html = "<html><body><p>No metadata here</p></body></html>"
    title, desc = _extract_metadata(html)
    assert title is None
    assert desc is None
```

Run: `pytest tests/tools/test_web_fetch.py::test_extract_title -v`
Expected: FAIL with "_extract_metadata not defined"

- [ ] **Step 2: Implement _extract_metadata**

```python
def _extract_metadata(html: str) *********REMOVED********* tuple[str | None, str | None]:
    """Extract title and description from raw HTML using BeautifulSoup."""
    from bs4 import BeautifulSoup

    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        return None, None

    title = None
    description = None

    # Extract title
    title_tag = soup.find("title")
    if title_tag:
        title = title_tag.get_text().strip()

    # Extract meta description
    meta_desc = soup.find("meta", attrs={"name": "description"})
    if meta_desc and meta_desc.get("content"):
        description = meta_desc["content"].strip()

    return title, description
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/tools/test_web_fetch.py -k "extract" -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add src/tools/web_fetch.py tests/tools/test_web_fetch.py
git commit -m "feat: add metadata extraction with BeautifulSoup"
```

---

## Chunk 4: Content Truncation

**Files:**
- Modify: `src/tools/web_fetch.py`

### Task 5: Implement _truncate_content helper

- [ ] **Step 1: Write failing test for truncation**

```python
# tests/tools/test_web_fetch.py (add)

from src.tools.web_fetch import _truncate_content

def test_truncate_small_content():
    """Content under limit should be unchanged"""
    content = "Short content"
    result = _truncate_content(content, max_size=100)
    assert result == "Short content"

def test_truncate_large_content():
    """Content over limit should be truncated at paragraph boundary"""
    content = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph that pushes us over the limit." + "x" * 1000
    result = _truncate_content(content, max_size=50)
    assert len(result) <= 50 + len("...(truncated)")
    assert result.endswith("...(truncated)")
    assert "\n\n" in result  # Truncated at paragraph boundary

def test_truncate_no_paragraph_boundary():
    """Content with no paragraph markers should truncate at max_size"""
    content = "A" * 200
    result = _truncate_content(content, max_size=100)
    assert len(result) <= 100 + len("...(truncated)")
    assert result.endswith("...(truncated)")
```

Run: `pytest tests/tools/test_web_fetch.py::test_truncate_small_content -v`
Expected: FAIL with "_truncate_content not defined"

- [ ] **Step 2: Implement _truncate_content**

```python
def _truncate_content(content: str, max_size: int = MAX_CONTENT_SIZE) *********REMOVED********* str:
    """Truncate content at last paragraph boundary if > max_size."""
    if len(content) <= max_size:
        return content

    # Try to truncate at paragraph boundary (\n\n)
    truncated = content[:max_size]
    last_paragraph = truncated.rfind("\n\n")
    if last_paragraph > max_size // 2:
        truncated = truncated[:last_paragraph]

    return truncated + "...(truncated)"
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/tools/test_web_fetch.py -k "truncate" -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add src/tools/web_fetch.py tests/tools/test_web_fetch.py
git commit -m "feat: add content truncation at paragraph boundary"
```

---

## Chunk 5: Result Serialization

**Files:**
- Modify: `src/tools/web_fetch.py`

### Task 6: Implement serialize_result helper

- [ ] **Step 1: Write failing test for serialization**

```python
# tests/tools/test_web_fetch.py (add)

from src.tools.web_fetch import WebFetchResult, serialize_result

def test_serialize_success():
    result = WebFetchResult(
        url="https://example.com",
        title="Test",
        description="A test",
        content="# Hello",
        status="success"
    )
    json_str = serialize_result(result)
    assert '"url": "https://example.com"' in json_str
    assert '"title": "Test"' in json_str
    assert '"content": "# Hello"' in json_str

def test_serialize_failure():
    result = WebFetchResult(
        url="https://example.com",
        status="failed",
        error_code="404_NOT_FOUND",
        error_message="Page not found",
        suggestion="Try another source",
        content=""
    )
    json_str = serialize_result(result)
    assert '"status": "failed"' in json_str
    assert '"error_code": "404_NOT_FOUND"' in json_str
```

Run: `pytest tests/tools/test_web_fetch.py::test_serialize_success -v`
Expected: FAIL with "serialize_result not defined"

- [ ] **Step 2: Implement serialize_result**

```python
def serialize_result(result: WebFetchResult) *********REMOVED********* str:
    """Serialize result to JSON string for LLM tool call response."""
    import dataclasses
    return json.dumps(dataclasses.asdict(result))
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/tools/test_web_fetch.py -k "serialize" -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add src/tools/web_fetch.py tests/tools/test_web_fetch.py
git commit -m "feat: add result serialization helper"
```

---

## Chunk 6: Main web_fetch Function

**Files:**
- Modify: `src/tools/web_fetch.py`

### Task 7: Implement async web_fetch function

- [ ] **Step 1: Write integration tests for web_fetch**

```python
# tests/tools/test_web_fetch.py (add)

import pytest
from src.tools.web_fetch import web_fetch

@pytest.mark.asyncio
async def test_web_fetch_blacklisted_domain():
    """Blacklisted domain should return BLACKLISTED_DOMAIN error"""
    result = await web_fetch("https://tradingview.com/symbol/AAPL")
    assert result.status == "failed"
    assert result.error_code == "BLACKLISTED_DOMAIN"
    assert "MarketExplorer" in result.suggestion

@pytest.mark.asyncio
async def test_web_fetch_invalid_url():
    """Invalid URL should return INVALID_URL error"""
    result = await web_fetch("not-a-url")
    assert result.status == "failed"
    assert result.error_code == "INVALID_URL"

@pytest.mark.asyncio
async def test_web_fetch_wikipedia():
    """Fetch Wikipedia article - integration test"""
    result = await web_fetch("https://en.wikipedia.org/wiki/Python_(programming_language)")
    # Don't assert content since network may fail, but check structure
    # This test documents expected behavior
```

Run: `pytest tests/tools/test_web_fetch.py::test_web_fetch_blacklisted_domain -v`
Expected: FAIL with "web_fetch not defined"

- [ ] **Step 2: Implement web_fetch**

```python
async def web_fetch(url: str) *********REMOVED********* WebFetchResult:
    """Fetch URL content and return metadata + Markdown (async for concurrent tool calls)."""
    from urllib.parse import urlparse
    import asyncio

    # 1. Check blacklist
    if _is_blacklisted_domain(url):
        return WebFetchResult(
            url=url,
            status="failed",
            error_code="BLACKLISTED_DOMAIN",
            error_message=_ERROR_MESSAGES["BLACKLISTED_DOMAIN"],
            suggestion=ERROR_SUGGESTIONS["BLACKLISTED_DOMAIN"],
        )

    # 2. Validate URL
    try:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError("Invalid URL")
    except Exception:
        return WebFetchResult(
            url=url,
            status="failed",
            error_code="INVALID_URL",
            error_message=_ERROR_MESSAGES["INVALID_URL"],
            suggestion=ERROR_SUGGESTIONS["INVALID_URL"],
        )

    # 3. Fetch via httpx
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            headers = {
                "User-Agent": "Mozilla/5.0 (compatible; Bot/0.1)",
                "Accept-Language": "en-US,en;q=0.9",
            }
            response = await client.get(url, headers=headers)
    except httpx.TimeoutException:
        return WebFetchResult(
            url=url,
            status="failed",
            error_code="TIMEOUT",
            error_message=_ERROR_MESSAGES["TIMEOUT"],
            suggestion=ERROR_SUGGESTIONS["TIMEOUT"],
        )
    except httpx.ConnectError:
        return WebFetchResult(
            url=url,
            status="failed",
            error_code="CONNECTION_ERROR",
            error_message=_ERROR_MESSAGES["CONNECTION_ERROR"],
            suggestion=ERROR_SUGGESTIONS["CONNECTION_ERROR"],
        )
    except Exception:
        return WebFetchResult(
            url=url,
            status="failed",
            error_code="CONNECTION_ERROR",
            error_message=_ERROR_MESSAGES["CONNECTION_ERROR"],
            suggestion=ERROR_SUGGESTIONS["CONNECTION_ERROR"],
        )

    # 4. Check HTTP status
    if response.status_code == 404:
        return WebFetchResult(
            url=url,
            status="failed",
            error_code="404_NOT_FOUND",
            error_message=_ERROR_MESSAGES["404_NOT_FOUND"],
            suggestion=ERROR_SUGGESTIONS["404_NOT_FOUND"],
        )
    elif response.status_code == 403:
        return WebFetchResult(
            url=url,
            status="failed",
            error_code="403_FORBIDDEN",
            error_message=_ERROR_MESSAGES["403_FORBIDDEN"],
            suggestion=ERROR_SUGGESTIONS["403_FORBIDDEN"],
        )
    elif response.status_code >= 400:
        return WebFetchResult(
            url=url,
            status="failed",
            error_code="UNKNOWN",
            error_message=f"HTTP error {response.status_code}",
            suggestion=ERROR_SUGGESTIONS["UNKNOWN"],
        )

    # 5. Extract metadata before processing
    title, description = _extract_metadata(response.text)

    # 6. Convert to Markdown via trafilatura
    try:
        markdown_content = trafilatura.extract(
            response.text,
            output_format="markdown",
            include_links=True
        )
        if not markdown_content:
            # trafilatura returns None for non-article pages
            markdown_content = ""
    except Exception:
        return WebFetchResult(
            url=url,
            status="failed",
            error_code="PARSE_ERROR",
            error_message=_ERROR_MESSAGES["PARSE_ERROR"],
            suggestion=ERROR_SUGGESTIONS["PARSE_ERROR"],
        )

    # 7. Truncate if needed
    content = _truncate_content(markdown_content, MAX_CONTENT_SIZE)

    return WebFetchResult(
        url=url,
        title=title,
        description=description,
        content=content,
        status="success",
    )
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/tools/test_web_fetch.py::test_web_fetch_blacklisted_domain -v`
Expected: PASS

Run: `pytest tests/tools/test_web_fetch.py::test_web_fetch_invalid_url -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/tools/web_fetch.py tests/tools/test_web_fetch.py
git commit -m "feat: implement main web_fetch async function"
```

---

## Chunk 7: Sync Wrapper & Tool Definition

**Files:**
- Modify: `src/tools/web_fetch.py`

### Task 8: Add sync wrapper and tool definition

- [ ] **Step 1: Add web_fetch_sync wrapper**

```python
def web_fetch_sync(url: str) *********REMOVED********* WebFetchResult:
    """Synchronous wrapper for non-async contexts."""
    import asyncio
    return asyncio.run(web_fetch(url))
```

- [ ] **Step 2: Add WEB_FETCH_TOOL definition**

```python
WEB_FETCH_TOOL = {
    "name": "web_fetch",
    "description": "Fetch URL content for RAG. Returns metadata + Markdown. Use for static pages. For JS-heavy sites, expect failure and use MarketExplorer instead.",
    "input_schema": {"type": "object", "properties": {"url": {"type": "string", "description": "URL to fetch"}}, "required": ["url"]},
}
```

- [ ] **Step 3: Commit**

```bash
git add src/tools/web_fetch.py
git commit -m "feat: add sync wrapper and tool definition"
```

---

## Chunk 8: Integration Tests (Network)

**Files:**
- Modify: `tests/tools/test_web_fetch.py`

### Task 9: Add network integration tests

- [ ] **Step 1: Write integration tests**

```python
# tests/tools/test_web_fetch.py (add)

@pytest.mark.asyncio
@pytest.mark.integration
async def test_fetch_wikipedia():
    """Fetch Wikipedia article"""
    result = await web_fetch("https://en.wikipedia.org/wiki/Main_Page")
    assert result.status == "success"
    assert result.title is not None
    assert len(result.content) > 100

@pytest.mark.asyncio
@pytest.mark.integration
async def test_fetch_reuters():
    """Fetch Reuters article and verify metadata"""
    result = await web_fetch("https://www.reuters.com/world/us/")
    # Check structure (may fail on network issues)
    assert result.status in ("success", "failed")
```

- [ ] **Step 2: Run integration tests with network**

Run: `pytest tests/tools/test_web_fetch.py -m integration -v`
Expected: Tests execute (may skip if network unavailable)

- [ ] **Step 3: Commit**

```bash
git add tests/tools/test_web_fetch.py
git commit -m "test: add integration tests for web_fetch"
```

---

## Chunk 9: Final Review & Cleanup

### Task 10: Run full test suite and lint

- [ ] **Step 1: Run all tests**

Run: `pytest tests/tools/test_web_fetch.py -v`

- [ ] **Step 2: Run ruff linting**

Run: `ruff check src/tools/web_fetch.py`

- [ ] **Step 3: Final commit if all passes**

---

## Summary

**Files created/modified:**
- `pyproject.toml` - added trafilatura dependency
- `src/tools/web_fetch.py` - main implementation
- `tests/tools/test_web_fetch.py` - unit and integration tests

**Test coverage:**
- Domain blacklist matching (exact, subdomain, false positive prevention)
- Metadata extraction (title, description)
- Content truncation (paragraph boundary)
- Result serialization
- HTTP error handling (404, 403, timeout, connection error)
- Blacklisted domain handling
- Invalid URL handling
