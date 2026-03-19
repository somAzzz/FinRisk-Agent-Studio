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
- Wraps `agent-browser` CLI for Python-first usage
- Methods: `navigate()`, `click()`, `type()`, `screenshot()`, `get_snapshot()`, `scroll()`, `wait_for()`
- Supports sync mode (blocking) and async mode (background execution)
- Returns structured results to LLM

**2. MarketExplorer (LLM Agent)**
- Receives exploration goal from user
- Plans browser action sequence
- Executes via BrowserWrapper
- Evaluates if new discoveries were made
- Decides to continue or stop

**3. Checkpoint Mechanism**
- Every N steps, pause for user confirmation
- User can inspect current findings, redirect, or terminate

## Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Integration pattern | CLI wrapper | Simple, debuggable, aligns with existing Python patterns |
| Operation mode | Sync for simple ops, async for multi-step tasks | Balance simplicity with performance |
| Exploration control | Discovery-based stopping | LLM judges if new info found, stops when stale |
| User involvement | Checkpoint nodes | Hybrid autonomy with human oversight |

## Data Flow

1. User provides goal (e.g., "Explore Apple's latest earnings and industry news")
2. MarketExplorer receives goal, plans initial steps
3. BrowserWrapper executes via `agent-browser` CLI
4. Results (snapshots, screenshots, page content) returned to LLM
5. LLM analyzes findings, judges novelty
6. If new discoveries: continue to next step
7. If stale: summarize and present to user
8. At checkpoints: user reviews and decides to continue/modify/stop

## File Structure Changes

```
FinText-LLM/
├── src/
│   ├── browser/                    # NEW
│   │   ├── __init__.py
│   │   ├── wrapper.py              # BrowserWrapper class
│   │   └── explorer.py             # MarketExplorer agent
│   ├── llm/
│   │   └── client.py               # Existing EdgarLLMClient
│   └── ...
├── docker-compose.yml              # May need Chrome dependency
├── pyproject.toml                  # Add agent-browser or chromium
└── README.md
```

## Dependencies

- `agent-browser` CLI installed in environment
- Chrome for Testing (auto-downloaded by agent-browser or system Chrome)
- Python subprocess for CLI invocation

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| LLM infinite loops | Discovery-based stopping + fixed step limit |
| Unresponsive pages | Timeout per operation, skip and continue |
| Resource exhaustion | Per-task step/token budget |
| Chrome crashes | Daemon restart on failure |

## Success Criteria

- LLM can autonomously browse 3+ financial sites and synthesize findings
- User can intervene at checkpoints to redirect or stop
- Exploration stops when no new information is discovered
- Results integrate with existing EDGAR analysis workflow
