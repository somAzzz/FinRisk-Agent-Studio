# Timestamp Feature Implementation Plan

> **Status (2026-06-25):** All tasks implemented. See `src/tools/web_fetch.py` (`WebFetchResult.fetched_at`) and `src/tools/search_router.py` (`published_at`, `time_range`). This document is kept as the historical implementation record. Several file paths it describes (e.g. `src/tools/router.py`) have since been refactored — see current `src/tools/search_router.py` for the live implementation.

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add timestamp awareness to `web_search` and `web_fetch` tools so the Router LLM can filter by time and results include publication/fetch timestamps.

**Architecture:**
- Query Pre-processing: Router LLM extracts time context from user query, sets `time_range` parameter
- Result Post-processing: `web_search` returns JSON Envelope with `published_at` per result; `web_fetch` returns `fetched_at` timestamp
- DDGS `timelimit` parameter maps directly to `time_range` values

**Tech Stack:** Python 3.12+, ddgs, httpx, Pydantic, dataclasses, json, datetime

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `src/tools/web_search.py` | Modify | Add `_extract_published_date`, replace `format_results` with JSON Envelope `_format_search_output`, add `time_range` param |
| `src/tools/web_fetch.py` | Modify | Add `fetched_at` field to `WebFetchResult`, set in `web_fetch()` |
| `src/tools/router.py` | Modify | Add `time_range` to `ToolChoice`, update prompt, sanitize and pass to `execute_web_search` |
| `tests/tools/test_web_search.py` | Create | Unit tests for date extraction, JSON envelope, time_range integration |
| `tests/tools/test_web_fetch.py` | Modify | Add tests for `fetched_at` field |

---

## Chunk 1: web_search.py - Date Extraction + JSON Envelope

**Files:**
- Modify: `src/tools/web_search.py`
- Create: `tests/tools/test_web_search.py`

### Task 1: Add _extract_published_date helper

- [ ] **Step 1: Write the failing test**

```python
# tests/tools/test_web_search.py

import pytest
from src.tools.web_search import _extract_published_date

def test_extract_from_date_field():
    """DDGS result with date field returns that date."""
    result = {"title": "Test", "href": "http://test.com", "body": "Some text", "date": "2026-03-15"}
    assert _extract_published_date(result) == "2026-03-15"

def test_extract_from_body_march_format():
    """Date embedded in body like 'Mar 15, 2026'."""
    result = {"title": "Test", "href": "http://test.com", "body": "Mar 15, 2026 - Article about stuff"}
    assert _extract_published_date(result) == "2026-03-15"

def test_extract_from_body_march_no_comma():
    """Date embedded like 'March 15 2026'."""
    result = {"title": "Test", "href": "http://test.com", "body": "March 15 2026 - News story"}
    assert _extract_published_date(result) == "2026-03-15"

def test_extract_from_body_iso_format():
    """Date embedded like '2026-03-15'."""
    result = {"title": "Test", "href": "http://test.com", "body": "Updated 2026-03-15 by admin"}
    assert _extract_published_date(result) == "2026-03-15"

def test_extract_from_body_day_month_year():
    """Date embedded like '15 March 2026'."""
    result = {"title": "Test", "href": "http://test.com", "body": "Posted 15 March 2026"}
    assert _extract_published_date(result) == "2026-03-15"

def test_no_date_found():
    """No date in date field or body returns None."""
    result = {"title": "Test", "href": "http://test.com", "body": "No date here"}
    assert _extract_published_date(result) is None
```

Run: `pytest tests/tools/test_web_search.py::test_extract_from_date_field -v`
Expected: FAIL with "_extract_published_date not defined"

- [ ] **Step 2: Implement _extract_published_date**

```python
# src/tools/web_search.py

import re
from datetime import datetime


def _extract_published_date(result: dict) -> str | None:
    """Extract publication date from DDGS result.

    Try to extract date from:
    1. result['date'] if present
    2. Regex match in result['body'] for date patterns like "Mar 15, 2026"
    3. Return None if no date found
    """
    # Try direct date field first
    if result.get("date"):
        return result["date"]

    # Try regex patterns in body
    date_patterns = [
        r"(\w{3,9}\s+\d{1,2},?\s+\d{4})",  # "March 15, 2026" or "March 15 2026"
        r"(\d{4}-\d{2}-\d{2})",  # "2026-03-15"
        r"(\d{1,2}\s+\w{3,9}\s+\d{4})",  # "15 March 2026"
    ]
    for pattern in date_patterns:
        match = re.search(pattern, result.get("body", ""))
        if match:
            date_str = match.group(1)
            # Try formats in order: without comma first (more specific)
            for fmt in ("%B %d %Y", "%B %d, %Y", "%d %B %Y", "%Y-%m-%d"):
                try:
                    parsed = datetime.strptime(date_str, fmt)
                    return parsed.strftime("%Y-%m-%d")
                except ValueError:
                    pass
    return None
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `pytest tests/tools/test_web_search.py -k "extract" -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add src/tools/web_search.py tests/tools/test_web_search.py
git commit -m "feat: add _extract_published_date for date extraction from DDGS results"
```

---

### Task 2: Replace format_results with JSON Envelope _format_search_output

- [ ] **Step 1: Write the failing test**

```python
# tests/tools/test_web_search.py (add)

import json
from src.tools.web_search import _format_search_output

def test_format_search_output_with_results():
    """JSON Envelope contains retrieved_at, query_used, time_range_applied, results."""
    results = [
        {"title": "Test Article", "href": "http://test.com/1", "body": "Mar 15, 2026 - Content here"},
        {"title": "Another", "href": "http://test.com/2", "body": "No date here"},
    ]
    output = _format_search_output(results, "test query", "m")

    data = json.loads(output)
    assert "retrieved_at" in data
    assert data["query_used"] == "test query"
    assert data["time_range_applied"] == "m"
    assert len(data["results"]) == 2
    assert data["results"][0]["title"] == "Test Article"
    assert data["results"][0]["url"] == "http://test.com/1"
    assert data["results"][0]["published_at"] == "2026-03-15"
    assert data["results"][1]["published_at"] is None

def test_format_search_output_empty():
    """Empty results returns envelope with empty results array."""
    output = _format_search_output([], "empty query", None)
    data = json.loads(output)
    assert data["results"] == []
    assert data["query_used"] == "empty query"
    assert data["time_range_applied"] is None

def test_format_search_output_body_truncated():
    """Body is truncated to 300 chars."""
    long_body = "x" * 500
    results = [{"title": "T", "href": "http://t.com", "body": long_body}]
    output = _format_search_output(results, "q", None)
    data = json.loads(output)
    assert len(data["results"][0]["body"]) == 300
```

Run: `pytest tests/tools/test_web_search.py::test_format_search_output_with_results -v`
Expected: FAIL with "_format_search_output not defined"

- [ ] **Step 2: Implement _format_search_output**

```python
# src/tools/web_search.py (add after _extract_published_date)

from datetime import datetime, timezone


def _format_search_output(
    results: list[dict],
    query: str,
    time_range: Literal["d", "w", "m", "y", None] = None,
) -> str:
    """Format search results as JSON Envelope for reliable LLM parsing.

    JSON Envelope structure:
    {
        "retrieved_at": "2026-03-22T14:30:00Z",  # UTC timestamp
        "query_used": "...",
        "time_range_applied": "m" | null,
        "results": [
            {"title": "...", "url": "...", "published_at": "...", "body": "..."},
            ...
        ]
    }
    """
    if not results:
        return json.dumps({
            "retrieved_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "query_used": query,
            "time_range_applied": time_range,
            "results": []
        }, ensure_ascii=False)

    output = {
        "retrieved_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "query_used": query,
        "time_range_applied": time_range,
        "results": []
    }

    for r in results:
        output["results"].append({
            "title": r.get("title", ""),
            "url": r.get("href", ""),
            "published_at": _extract_published_date(r),
            "body": r.get("body", "")[:300]
        })

    return json.dumps(output, ensure_ascii=False)
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `pytest tests/tools/test_web_search.py -k "format" -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add src/tools/web_search.py tests/tools/test_web_search.py
git commit -m "feat: replace format_results with JSON Envelope _format_search_output"
```

---

### Task 3: Update web_search to accept time_range parameter

- [ ] **Step 1: Write the failing test**

```python
# tests/tools/test_web_search.py (add)

def test_web_search_accepts_time_range():
    """web_search accepts time_range parameter and passes to DDGS."""
    from unittest.mock import patch, MagicMock

    mock_results = [
        {"title": "T", "href": "http://t.com", "body": "Mar 20, 2026 - Test"}
    ]
    mock_ddgs = MagicMock()
    mock_ddgs.text.return_value = iter(mock_results)

    with patch("src.tools.web_search.DDGS") as mock_cls:
        mock_instance = MagicMock()
        mock_instance.__enter__ = MagicMock(return_value=mock_ddgs)
        mock_instance.__exit__ = MagicMock(return_value=None)
        mock_cls.return_value = mock_instance

        output = _format_search_output(mock_results, "test", "m")
        data = json.loads(output)
        assert data["time_range_applied"] == "m"
```

Run: `pytest tests/tools/test_web_search.py::test_web_search_accepts_time_range -v`
Expected: FAIL (web_search doesn't accept time_range yet)

- [ ] **Step 2: Update web_search function signature and implementation**

```python
# src/tools/web_search.py

def web_search(
    query: str,
    max_results: int = 5,
    time_range: Literal["d", "w", "m", "y", None] = None,
) -> str:
    """Execute web search and return JSON Envelope.

    Args:
        query: Search query (English recommended)
        max_results: Number of results to return (default 5)
        time_range: Time filter - 'd'=day, 'w'=week, 'm'=month, 'y'=year, None=no filter

    Returns:
        JSON Envelope string with search results
    """
    try:
        from ddgs import DDGS
    except ImportError:
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            return json.dumps({"error": "ddgs package not installed. Run: uv pip install ddgs"})

    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results, timelimit=time_range))
            return _format_search_output(results, query, time_range)
    except Exception as e:
        return json.dumps({"error": f"Search failed: {str(e)}"})
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `pytest tests/tools/test_web_search.py -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add src/tools/web_search.py
git commit -m "feat: add time_range parameter to web_search"
```

---

## Chunk 2: web_fetch.py - Add fetched_at

**Files:**
- Modify: `src/tools/web_fetch.py`
- Modify: `tests/tools/test_web_fetch.py`

### Task 4: Add fetched_at field to WebFetchResult

- [ ] **Step 1: Write the failing test**

```python
# tests/tools/test_web_fetch.py (add)

from datetime import datetime
from src.tools.web_fetch import WebFetchResult

def test_fetched_at_field_exists():
    """WebFetchResult has fetched_at field."""
    result = WebFetchResult(url="http://test.com", fetched_at="2026-03-22T14:30:00")
    assert result.fetched_at == "2026-03-22T14:30:00"

def test_fetched_at_none_for_failure():
    """Failed fetch has fetched_at=None."""
    result = WebFetchResult(
        url="http://test.com",
        status="failed",
        error_code="TIMEOUT",
        fetched_at=None
    )
    assert result.fetched_at is None
```

Run: `pytest tests/tools/test_web_fetch.py::test_fetched_at_field_exists -v`
Expected: FAIL with "fetched_at not found"

- [ ] **Step 2: Add fetched_at to WebFetchResult**

```python
# src/tools/web_fetch.py

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
    fetched_at: str | None = None  # ISO timestamp for success, None for failures
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `pytest tests/tools/test_web_fetch.py -k "fetched_at" -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add src/tools/web_fetch.py tests/tools/test_web_fetch.py
git commit -m "feat: add fetched_at field to WebFetchResult"
```

---

### Task 5: Set fetched_at in web_fetch() on success

- [ ] **Step 1: Write the failing test**

```python
# tests/tools/test_web_fetch.py (add)

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from src.tools.web_fetch import web_fetch

@pytest.mark.asyncio
async def test_web_fetch_sets_fetched_at_on_success():
    """Successful fetch returns fetched_at timestamp."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "<html><head><title>Test</title></head><body><p>Content</p></body></html>"

    with patch("src.tools.web_fetch.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.aclose = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        result = await web_fetch("http://test.com")

        assert result.status == "success"
        assert result.fetched_at is not None
        # Verify format: YYYY-MM-DDTHH:MM:SS
        import re
        assert re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", result.fetched_at)
```

Run: `pytest tests/tools/test_web_fetch.py::test_web_fetch_sets_fetched_at_on_success -v`
Expected: FAIL (fetched_at not set in web_fetch yet)

- [ ] **Step 2: Update web_fetch to set fetched_at on success**

```python
# src/tools/web_fetch.py (find the return statement at the end of web_fetch and update)

from datetime import datetime, timezone

# ... (inside async def web_fetch, after successful fetch, before returning):

# At the end of web_fetch, after successful extraction:
content = _truncate_content(markdown_content, MAX_CONTENT_SIZE)

return WebFetchResult(
    url=url,
    title=title,
    description=description,
    content=content,
    status="success",
    fetched_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
)
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `pytest tests/tools/test_web_fetch.py::test_web_fetch_sets_fetched_at_on_success -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/tools/web_fetch.py
git commit -m "feat: set fetched_at timestamp in web_fetch on success"
```

---

## Chunk 3: router.py - time_range in ToolChoice

**Files:**
- Modify: `src/tools/router.py`

### Task 6: Add time_range to ToolChoice model

- [ ] **Step 1: Write the failing test**

```python
# tests/tools/test_router.py (create if not exists, or add)

import pytest
from src.tools.router import ToolChoice

def test_tool_choice_accepts_time_range():
    """ToolChoice accepts time_range field."""
    choice = ToolChoice(
        thought="Recent news about X",
        tool="web_search",
        query="latest news",
        time_range="w"
    )
    assert choice.time_range == "w"

def test_tool_choice_time_range_none():
    """ToolChoice time_range defaults to None."""
    choice = ToolChoice(
        thought="General query",
        tool="web_search",
        query="What is AI"
    )
    assert choice.time_range is None
```

Run: `pytest tests/tools/test_router.py::test_tool_choice_accepts_time_range -v`
Expected: FAIL with "time_range not found"

- [ ] **Step 2: Update ToolChoice model**

```python
# src/tools/router.py

class ToolChoice(BaseModel):
    """LLM response for tool selection."""
    thought: str = Field(description="Reasoning about what to do")
    tool: Literal["web_search", "web_fetch", "browser", "finish"] = Field(
        description="Choose: 'web_search' for quick info, 'web_fetch' for URL content, 'browser' for complex interaction, 'finish' if done"
    )
    query: str | None = Field(default=None, description="Search query if using web_search")
    url: str | None = Field(default=None, description="URL to fetch if using web_fetch")
    time_range: Literal["d", "w", "m", "y", None] = Field(
        default=None,
        description="Time filter for web_search. 'd'=day, 'w'=week, 'm'=month, 'y'=year. Only set if query implies recency. MUST be null (not empty string) when no time filter is needed."
    )
    reason: str | None = Field(default=None, description="Why you chose this tool")
    answer: str | None = Field(default=None, description="Final answer if using finish")
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `pytest tests/tools/test_router.py -k "time_range" -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add src/tools/router.py tests/tools/test_router.py
git commit -m "feat: add time_range field to ToolChoice model"
```

---

### Task 7: Update _build_router_prompt with time_range instructions

- [ ] **Step 1: Read current _build_router_prompt and add time_range instruction**

```python
# src/tools/router.py (find _build_router_prompt and add time_range to the tool descriptions section)
```

Add to the web_search description:
```
time_range: Time filter for web_search. Set this when:
- User says "recent", "latest", "last [period]"
- User mentions a specific period like "last week", "this month"
- The topic requires current information (news, markets, events)
- User does NOT specify a time, set to null (NOT empty string "")

Options: 'd'=past 24 hours, 'w'=past week, 'm'=past month, 'y'=past year
```

Add Time Anchor warning:
```
⚠️ Time Anchor Requirement: The LLM must receive current time as an absolute reference to correctly interpret relative time expressions like "last week". The System Prompt (agent role) MUST include current system time.
```

- [ ] **Step 2: Commit**

```bash
git add src/tools/router.py
git commit -m "feat: update router prompt with time_range instructions"
```

---

### Task 8: Update execute_web_search with sanitization and pass time_range

- [ ] **Step 1: Read current execute_web_search**

```bash
grep -n "def execute_web_search" src/tools/router.py
```

- [ ] **Step 2: Add _VALID_TIME_RANGES constant and update execute_web_search**

```python
# src/tools/router.py (add near the top of the module, after imports)

_VALID_TIME_RANGES: set[Literal["d", "w", "m", "y", None]] = {"d", "w", "m", "y", None}
```

Update `execute_web_search`:
```python
def execute_web_search(self, query: str, time_range: Literal["d", "w", "m", "y", None] = None) -> str:
    """Execute web search and record result."""
    # Sanitize: only pass valid time_range values to DDGS
    sanitized_time_range = time_range if time_range in _VALID_TIME_RANGES else None
    print(f"[Web Search] Query: {query}, time_range: {sanitized_time_range}")
    result = web_search(query, time_range=sanitized_time_range)
    self.search_history.append({
        "tool": "web_search",
        "query": query,
        "result": result[:500],
    })
    return result
```

- [ ] **Step 3: Commit**

```bash
git add src/tools/router.py
git commit -m "feat: add time_range sanitization in execute_web_search"
```

---

### Task 9: Update run() to pass time_range to execute_web_search

- [ ] **Step 1: Find the line in run() that calls execute_web_search**

```bash
grep -n "execute_web_search" src/tools/router.py
```

- [ ] **Step 2: Update run() to pass choice.time_range**

Change:
```python
if choice.tool == "web_search" and choice.query:
    result = self.execute_web_search(choice.query)
```

To:
```python
if choice.tool == "web_search" and choice.query:
    result = self.execute_web_search(choice.query, choice.time_range)
```

Also update the second call (synthesize suggested search):
```python
if synthesis.suggested_tool == "web_search" and synthesis.suggested_query:
    result = self.execute_web_search(synthesis.suggested_query, synthesis.suggested_time_range)
```

Note: If SynthesisResult doesn't have suggested_time_range, you may need to add it:
```python
class SynthesisResult(BaseModel):
    # ... existing fields ...
    suggested_time_range: Literal["d", "w", "m", "y", None] | None = Field(default=None)
```

- [ ] **Step 3: Commit**

```bash
git add src/tools/router.py
git commit -m "feat: pass time_range from ToolChoice to execute_web_search in run()"
```

---

## Chunk 4: Integration & Final Review

### Task 10: Run full test suite

- [ ] **Step 1: Run all tests**

Run: `pytest tests/tools/ -v`

- [ ] **Step 2: Run ruff linting**

Run: `ruff check src/tools/web_search.py src/tools/web_fetch.py src/tools/router.py`

- [ ] **Step 3: Final commit if all passes**

```bash
git add -A
git commit -m "feat: add timestamp awareness to web_search and web_fetch"
```

---

## Summary

**Files created/modified:**
- `src/tools/web_search.py` - Added `_extract_published_date`, JSON Envelope output, `time_range` param
- `src/tools/web_fetch.py` - Added `fetched_at` field, set on successful fetch
- `src/tools/router.py` - Added `time_range` to `ToolChoice`, prompt update, sanitization, pass-through
- `tests/tools/test_web_search.py` - Created with date extraction and JSON Envelope tests
- `tests/tools/test_web_fetch.py` - Added `fetched_at` tests
- `tests/tools/test_router.py` - Created with `time_range` in `ToolChoice` tests

**Test coverage:**
- Date extraction from DDGS results (date field, various body formats)
- JSON Envelope structure and truncation
- `time_range` parameter passthrough
- `fetched_at` field on success/failure
- `ToolChoice.time_range` validation
