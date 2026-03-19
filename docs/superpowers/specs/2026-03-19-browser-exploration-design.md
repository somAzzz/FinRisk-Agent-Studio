# FinText-LLM Browser Exploration Integration Design

## Context

FinText-LLM is a SEC EDGAR filing analysis system using local LLM + Spark + Neo4j. Users want to enhance the LLM with browser capabilities to autonomously explore valuable financial information beyond static EDGAR filings — including real-time market data, news, and regulatory updates.

**Goal:** Integrate `agent-browser` (a Rust headless browser CLI) to enable LLM-driven web exploration in a hybrid mode where the LLM autonomously explores but the user can intervene at checkpoints.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  EdgarLLMClient (existing)                              │
│  ┌─────────────┐    ┌──────────────┐    ┌───────────┐ │
│  │ RiskExtract │    │MarketExplorer │    │PolicyScan │ │
│  └─────────────┘    └──────────────┘    └───────────┘ │
│                           │                            │
│                    ┌──────▼──────┐                     │
│                    │BrowserWrapper│  ← NEW             │
│                    │ (Python)    │                     │
│                    └──────┬──────┘                     │
│                           │                            │
│                    agent-browser CLI                   │
│                           │                            │
│                    Chrome (headless)                   │
└─────────────────────────────────────────────────────────┘
```

### Components

**1. BrowserWrapper (Python Class)**

Located at `src/browser/wrapper.py`.

```python
class BrowserResult(TypedDict):
    """Structured result from all browser operations."""
    success: bool
    content: str | None          # Text content from snapshot
    screenshot: str | None       # Base64-encoded PNG
    url: str                     # Current URL after operation
    error: str | None

class BrowserWrapper:
    def __init__(
        self,
        timeout: int = 30,
        checkpoint_interval: int = 5,
        max_steps: int = 20,
        headless: bool = True,
    ): ...

    def navigate(self, url: str) *********REMOVED********* BrowserResult: ...
    def click(self, selector: str) *********REMOVED********* BrowserResult: ...
    def type(self, selector: str, text: str) *********REMOVED********* BrowserResult: ...
    def scroll(self, direction: Literal["up", "down"], pixels: int = 500) *********REMOVED********* BrowserResult: ...
    def get_snapshot(self) *********REMOVED********* BrowserResult:
        """Returns AI-friendly accessibility tree as markdown."""
    def screenshot(self) *********REMOVED********* BrowserResult:
        """Returns base64-encoded PNG."""
    def wait_for(self, selector: str, timeout: int = 10) *********REMOVED********* BrowserResult: ...
    async def execute_batch(self, commands: list[dict]) *********REMOVED********* list[BrowserResult]: ...
    def close(self) *********REMOVED********* None: ...
```

**2. MarketExplorer (LLM Agent)**

Located at `src/browser/explorer.py`.

```python
@dataclass
class Finding:
    url: str
    content_hash: str          # SHA256 of page content
    summary: str               # LLM-generated summary
    timestamp: datetime
    source_type: Literal["news", "financial", "regulatory", "other"]

@dataclass
class ExplorationState:
    goal: str
    findings: list[Finding]
    visited_urls: set[str]
    current_step: int
    last_discovery: datetime

**LLM Client Extension**

The existing `EdgarLLMClient` only has `extract_risks()`. Extend it with a general-purpose method:

```python
class EdgarLLMClient:
    # ... existing methods ...

    def complete(
        self,
        prompt: str,
        system: str | None = None,
        max_tokens: int = 2048,
    ) *********REMOVED********* str:
        """General-purpose chat completion for browser exploration."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.3,  # Higher for exploration
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content

    def compute_embedding(self, text: str) *********REMOVED********* list[float]:
        """Compute text embedding for novelty detection.

        Uses sentence-transformers/all-MiniLM-L6-v2 for fast, local embedding.
        """
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer("all-MiniLM-L6-v2")
        return model.encode(text).tolist()
```

class MarketExplorer:
    def __init__(self, llm_client: EdgarLLMClient, wrapper: BrowserWrapper): ...

    async def explore(
        self,
        goal: str,
        checkpoint_callback: Callable[[ExplorationState], bool] | None = None,
    ) *********REMOVED********* ExplorationState:
        """
        Execute exploration goal.

        checkpoint_callback: returns True to continue, False to stop.
        Called every checkpoint_interval steps.
        """
```

**3. Checkpoint Mechanism**

User interaction via callable callback:

```python
async def checkpoint_handler(state: ExplorationState) *********REMOVED********* bool:
    """Return True to continue, False to stop."""
    print(f"Step {state.current_step}: {len(state.findings)} findings")
    for f in state.findings[-3:]:
        print(f"  - {f.summary[:100]}...")
    response = input("Continue exploration? [y/n]: ")
    return response.lower() == "y"

explorer = MarketExplorer(client, wrapper)
result = await explorer.explore(
    goal="Explore Apple earnings and industry news",
    checkpoint_callback=checkpoint_handler,
)
```

## CLI Integration

agent-browser commands and output format:

| Operation | CLI Command | Output |
|-----------|-------------|--------|
| Navigate | `agent-browser goto <url>` | JSON with url, title |
| Snapshot | `agent-browser snapshot` | Markdown accessibility tree |
| Screenshot | `agent-browser screenshot --path /tmp/.png` | PNG file + JSON metadata |
| Click | `agent-browser click "<selector>"` | JSON with new url, success |
| Type | `agent-browser type "<selector>" "<text>"` | JSON with input value |
| Scroll | `agent-browser scroll <direction> <pixels>` | JSON with scroll position |
| Wait | `agent-browser wait "<selector>" <timeout>` | JSON with element found |

All commands return JSON: `{"success": bool, "error": str|null, "data": {...}}`

## Novelty Detection

**Technical definition:** A discovery is considered "new" if:

1. Content hash (SHA256 of extracted text from page) differs from any previously recorded hash
2. LLM-generated summary contains information not in recent findings (cosine similarity < 0.85)

**Novelty Detection Flow:**
```
1. Page content obtained via get_snapshot()
2. Text extracted from accessibility tree
3. Hash computed (SHA256 of truncated text, first 10KB) for exact dedup
4. If hash is new → compute embedding via compute_embedding()
5. If recent embeddings exist → compute cosine similarity
6. If similarity < 0.85 → marked as NEW finding
7. If hash seen before → SKIP (no new content)
```

**Cosine similarity:**
```python
import numpy as np

def cosine_similarity(a: list[float], b: list[float]) *********REMOVED********* float:
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))
```

**Stopping conditions (any triggers stop):**
- Step limit reached (max_steps, default: 20)
- No new findings in 3 consecutive steps
- All hashes seen twice (thoroughly explored)
- Error rate > 50% in last 5 steps (likely blocked)

## Error Handling

| Error | Handling |
|-------|----------|
| Network timeout | Retry 2x with exponential backoff, then skip |
| Page crash during click/type | Restart Chrome session, retry operation once |
| Invalid selector | Log error, skip operation, continue |
| User non-response at checkpoint | Timeout 60s, default to stop |
| Chrome orphan process | Kill stale processes on init, health check on start |
| Anti-bot (403, CAPTCHA) | Skip URL, log warning, do not retry same path |
| Chrome fails to start | Log fatal error, raise `BrowserError`, do not continue |
| agent-browser binary not found | Health check on init, clear error message with install instructions |
| Malformed JSON in CLI output | Retry once, then fail with parse error |
| Screenshot command fails (disk full) | Log error, return `BrowserResult` with `screenshot: None` |
| Page never loads (infinite spinner) | `wait_for` has max timeout, then fail |
| Non-http(s) URL passed to navigate | Validate URL scheme, raise `ValueError` |

**Sensitive Data Filter (regex patterns):**
```python
import re

SENSITIVE_PATTERNS = [
    (r"\b\d{3}-\d{2}-\d{4}\b", "[SSN]"),          # SSN
    (r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b", "[CARD]"),  # Credit card
    (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "[EMAIL]"),  # Email
    (r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b", "[PHONE]"),  # Phone
    (r"sk-[A-Za-z0-9]{48}", "[API_KEY]"),           # OpenAI API key
    (r"xox[baprs]-[A-Za-z0-9]{10,}", "[TOKEN]"),    # Slack token
]

def sanitize_snapshot(text: str) *********REMOVED********* str:
    for pattern, replacement in SENSITIVE_PATTERNS:
        text = re.sub(pattern, replacement, text)
    return text
```

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `timeout` | 30 | Seconds per browser operation |
| `checkpoint_interval` | 5 | Steps between user checkpoints |
| `max_steps` | 20 | Hard limit on exploration steps |
| `novelty_threshold` | 0.85 | Embedding similarity below = new |
| `no_new_findings_limit` | 3 | Consecutive steps with no new = stop |
| `error_rate_threshold` | 0.5 | Max error ratio before abort |

## File Structure Changes

```
FinText-LLM/
├── src/
│   ├── browser/                    # NEW
│   │   ├── __init__.py
│   │   ├── wrapper.py              # BrowserWrapper class
│   │   ├── explorer.py             # MarketExplorer agent
│   │   └── config.py               # Configuration dataclasses
│   ├── llm/
│   │   └── client.py               # Existing EdgarLLMClient
│   └── ...
├── docker-compose.yml              # Add Chrome dependency
├── pyproject.toml                  # Add chromium or agent-browser
└── README.md
```

## Dependencies

- `agent-browser` CLI (`pip install agent-browser` or binary)
- Chrome for Testing (auto-downloaded by agent-browser)
- Python 3.12+, standard library + `subprocess`, `asyncio`, `hashlib`
- `sentence-transformers` (for embeddings)
- `numpy` (for cosine similarity)

## Findings Export Schema

```python
{
    "goal": "Explore Apple earnings and industry news",
    "findings": [
        {
            "url": "https://finance.yahoo.com/news/apple-q4-earnings-123",
            "content_hash": "sha256:e3b0c44298fc1c149afb4c8996fb92427ae41e4649...",
            "summary": "Apple reported Q4 earnings beating estimates with strong iPhone sales...",
            "timestamp": "2026-03-19T10:30:00Z",
            "source_type": "financial"  # news | financial | regulatory | other
        }
    ],
    "visited_urls": [
        "https://finance.yahoo.com",
        "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&AAPL"
    ],
    "total_steps": 12,
    "stopped_reason": "max_steps",  # max_steps | user_stop | no_new_findings | error
    "final_state": {
        "new_findings_count": 5,
        "unique_domains": 3,
        "error_rate": 0.08
    }
}
```

## Rate Limiting

- Random delay between operations: 1-3 seconds (uniform random)
- Respect `robots.txt` when discoverable (check before visiting domain)
- Exponential backoff on 429/503 responses: 2^x seconds, max 60s, max 3 retries

## Success Criteria (Measurable)

| Criterion | Metric |
|-----------|--------|
| Multi-site exploration | Successfully browse 3 distinct domains in single run |
| Synthesis quality | At least 80% of findings contain unique, non-duplicate content |
| Checkpoint works | User can intervene and redirect at checkpoint |
| Graceful stopping | Exploration stops within 2 steps of hitting no-new-findings limit |
| Error resilience | < 10% step failure rate on typical financial sites |
| Integration | Findings exportable as structured dict, can feed into existing analysis |

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| LLM infinite loops | Discovery-based stopping + hard max_steps=20 |
| Unresponsive pages | 30s timeout per op, skip and continue |
| Resource exhaustion | Per-task step budget, process cleanup on exit |
| Chrome crashes | Health check on init, restart on failure, kill orphans |
| Anti-bot detection | Exponential backoff, skip blocked URLs |
| Sensitive data exposure | Regex filter on snapshots before LLM |
| Rate limiting/bans | Respect robots.txt, random delay between ops |
