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

1. Content hash (SHA256 of page text) differs from any previously recorded hash
2. LLM-generated summary contains information not in recent findings (semantic similarity < 0.85 via embedding)

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
| Sensitive data in snapshot | Filter before LLM: redact SSN, credit card patterns |

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
