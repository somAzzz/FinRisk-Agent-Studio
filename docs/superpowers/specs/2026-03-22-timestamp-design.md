# Timestamp Feature for Web Search and Web Fetch

## Overview

Add timestamp awareness to `web_search` and `web_fetch` tools so that the LLM and search results both understand the user's temporal context when querying ("recent Middle East war", "2024 earnings", etc.).

## Architecture

### Design: Bidirectional Enhancement

1. **Query Pre-processing** - Router LLM extracts time context from user query
2. **Result Post-processing** - Results include publication/fetch timestamps

### Data Flow

```
User query: "recent Middle East war impact on oil prices"
    ↓
Router LLM analyzes query → decides time_range = "m" (last month)
    ↓
web_search(query, time_range="m") → DDGS API with time filter
    ↓
SearchResult(title, url, body, published_at="2026-03-15")
    ↓
web_fetch(url) → WebFetchResult with fetched_at="2026-03-22"
    ↓
LLM synthesis understands results are temporally relevant
```

## Implementation

### 1. ToolChoice Model Update

Modify `src/tools/router.py`:

```python
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
        description="Time filter for web_search. 'd'=day, 'w'=week, 'm'=month, 'y'=year. Only set if query implies recency."
    )
    reason: str | None = Field(default=None, description="Why you chose this tool")
    answer: str | None = Field(default=None, description="Final answer if using finish")
```

### 2. SearchResult Model Update

Modify `src/tools/web_search.py`:

```python
class SearchResult(BaseModel):
    """Single search result."""
    title: str
    url: str
    body: str
    published_at: str | None = None  # Publication date if available
```

### 3. WebFetchResult Model Update

Modify `src/tools/web_fetch.py`:

```python
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
    fetched_at: str | None = None  # When the page was fetched
```

### 4. web_search Function Update

Modify `src/tools/web_search.py`:

```python
def web_search(query: str, max_results: int = 5, time_range: Literal["d", "w", "m", "y", None] = None) *********REMOVED********* str:
    """Execute web search with optional time filter.

    Args:
        query: Search query (English recommended)
        max_results: Number of results to return (default 5)
        time_range: Time filter - 'd'=day, 'w'=week, 'm'=month, 'y'=year

    Returns:
        Formatted string with search results including publication dates
    """
    # Pass time_range to DDGS if provided
    with DDGS() as ddgs:
        results = list(ddgs.text(query, max_results=max_results, timelimit=time_range))
        return format_results(results)
```

### 5. Router Prompt Update

Update `_build_router_prompt` in `src/tools/router.py` to instruct LLM on time_range:

```
time_range: Time filter for web_search. Set this when:
- User says "recent", "latest", "last [period]"
- User mentions a specific period like "last week", "this month"
- The topic requires current information (news, markets, events)
- User does NOT specify a time, leave as null

Options: 'd'=past 24 hours, 'w'=past week, 'm'=past month, 'y'=past year
```

### 6. Router execute_web_search Update

```python
def execute_web_search(self, query: str, time_range: Literal["d", "w", "m", "y", None] = None) *********REMOVED********* str:
    """Execute web search and record result."""
    print(f"[Web Search] Query: {query}, time_range: {time_range}")
    result = web_search(query, time_range=time_range)
    # ... rest unchanged
```

### 7. Router run() Update

Update `run()` to pass `time_range` from `ToolChoice` to `execute_web_search`:

```python
if choice.tool == "web_search" and choice.query:
    result = self.execute_web_search(choice.query, choice.time_range)
```

## DDGS time_range Mapping

DDGS (DuckDuckGo) uses `timelimit` parameter:
- `d` → `d` (past day)
- `w` → `w` (past week)
- `m` → `m` (past month)
- `y` → `y` (past year)
- `None` → no filter

## Extracted Date Format

From search results, try to extract publication date in `YYYY-MM-DD` format from:
- DDGS result metadata if available
- Parse from result body/snippet if date pattern found

If no date found, `published_at` remains `None`.

## fetched_at Format

`fetched_at` uses ISO format: `YYYY-MM-DDTHH:MM:SS` (e.g., `"2026-03-22T14:30:00"`)

## Testing

### Unit Tests

| Test | Description |
|------|-------------|
| `test_time_range_none` | Query without time context → time_range=None |
| `test_time_range_recent` | Query "recent news" → time_range="w" |
| `test_time_range_specific` | Query "last month" → time_range="m" |
| `test_search_result_with_date` | Search result includes published_at |
| `test_fetch_result_with_fetched_at` | Fetch result includes fetched_at |

### Integration Tests

| Test | Description |
|------|-------------|
| `test_search_with_time_filter` | web_search(query, time_range="m") returns recent results |
| `test_router_extracts_time_range` | Router LLM correctly extracts time from query |

## Files to Modify

| File | Changes |
|------|---------|
| `src/tools/web_search.py` | Add `time_range` param, `published_at` field, update DDGS call |
| `src/tools/web_fetch.py` | Add `fetched_at` field, set in web_fetch() |
| `src/tools/router.py` | Add `time_range` to ToolChoice, update prompt, pass to execute |

## Notes

- time_range only affects web_search (web_fetch gets fetched_at for context)
- LLM decides time_range based on query temporal context
- published_at may be None if date extraction fails
- fetched_at is always set for successful fetches
