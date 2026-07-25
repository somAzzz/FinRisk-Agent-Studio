# FinRisk Agent Studio

Evidence-first financial research workbench for SEC filing analysis, point-in-time company snapshots, peer analysis, valuation, monitoring, graph reasoning, supply-chain exploration, runtime quality guardrails, and human review.

FinRisk Agent Studio is an open-source reference implementation for financial research workflows. It is not a generic "chat with filings" demo. The project focuses on auditable agent execution: structured inputs, tool traces, evidence candidates, deterministic scoring, graph paths, quality gates, and reviewable outputs.

Current documentation version: **v0.1 release candidate**. Python and frontend package version: `0.1.0`.

## Live Demo

```text
https://somazzz.github.io/FinRisk-Agent-Studio/
```

The hosted GitHub Pages version is a static dashboard backed by offline fixtures. It shows the FinRisk workflow timeline, risk report, evidence graph, score breakdown, and evaluation guardrails without requiring API keys, a backend, GPU, Neo4j, or live network access.

## What Works Today

- **FinRisk workflow API**: queued/background FastAPI runs for SEC filing risk extraction, market evidence, normalization, scoring, graph reasoning, report generation, and evaluation.
- **Runtime quality layer**: schema checks, claim/evidence grounding, source quality, financial-safety checks, graph-path validation, fallback tracking, and human-review status.
- **Graph reasoning subsystem**: context building, candidate path retrieval, path scoring, evidence binding, safe path interpretation, and graph insight validation.
- **React workflow console**: launcher, run history, process monitor, timeline, risk report, score breakdown, evidence graph, evaluation panel, claim/evidence matrix, supply-chain explorer, and agent-run trace UI.
- **Product supply-chain explorer**: evidence-backed product dependency discovery, recursive expansion, Sankey visualization, graph writer path, observability metrics, and quality verdicts.
- **LLM-driven agent runs**: `/agent-runs` API with provider/tool-loop settings, tool traces, evidence candidates, redacted trace download, and human review actions.
- **Provider-neutral tool loop**: OpenAI-compatible structured outputs, native tool calling where supported, JSON fallback, budget controls, and no-tool finalization.
- **Evidence and data tools**: SEC EDGAR, filing sections, transcripts, XBRL/financial metrics, web search/fetch, browser exploration, search routing, caching, and provider fallbacks.
- **Memory/context guardrails**: evidence-memory adapters, graph-edge memory, active/candidate lifecycle rules, and write guardrails for hypothesis or untrusted evidence.
- **Personal research cycle**: immutable company snapshots, thesis/watchlist journal, expectations, material-change review, alerts, post-earnings review, and direct FinRisk-to-snapshot orchestration.
- **Financial fact layer**: auditable SEC aliases, industry templates, original/amended/latest-known restatement policies, TTM and quarter derivations, and live reconciliation across AAPL, NVDA, XOM, JPM, and TSM.
- **Peer Analysis**: saved peer groups, SEC SIC candidate suggestions with analyst confirmation, fiscal-period/currency safeguards, freshness disclosure, and separate financial, risk, expectation, and valuation layers.
- **Valuation and monitoring**: scenario valuation, sensitivity matrices, P/E, EV/EBITDA, FCF yield, simplified DCF, immutable assumption history, request throttling/retries, source cursors, and local scheduler templates.
- **Deployment path**: GitHub Pages static dashboard published from `gh-pages`; local full-stack mode runs FastAPI + Vite.

## Current Workflow Shape

```text
Company Resolver
→ Filing Risk Extraction
→ Market Evidence Collection
→ Evidence Normalization
→ Risk Scoring
→ Graph Reasoning
→ Structured Report Generation
→ Quality Layer / Human Review Gate
```

Graph reasoning is handled as a controlled subsystem:

```text
Graph Context Builder
→ Candidate Path Retriever
→ Path Scorer
→ Evidence Binder
→ LLM / Template Path Interpreter
→ Graph Insight Validator
→ Evidence Graph Payload
```

LLMs explain verified paths and generate research hypotheses. They do not create unsupported graph facts or issue buy/sell recommendations.

## Quick Start

Install Python dependencies:

```bash
uv sync
```

Install frontend dependencies:

```bash
cd frontend
npm ci
```

Run backend locally:

```bash
AUTH_DISABLED=1 RATE_LIMIT_DISABLED=1 \
uv run uvicorn src.api.main:app --host 127.0.0.1 --port 8000
```

Run frontend locally in a second terminal:

```bash
cd frontend
npm run dev
```

Open:

```text
http://127.0.0.1:5173/
```

The Vite dev server proxies `/workflows`, `/supply-chain`, `/agent-runs`, and `/research` to the FastAPI backend.

Initialize or upgrade the local research databases before the first run:

```bash
uv run python main.py database migrate --path .cache/research_snapshots.sqlite
uv run python main.py database migrate --path .cache/research_journal.sqlite
```

## Static Dashboard Build

Build the GitHub Pages static demo locally:

```bash
cd frontend
GITHUB_PAGES=true VITE_STATIC_DEMO=1 npm run build
```

Preview it:

```bash
npm run preview -- --host 127.0.0.1 --port 4173
```

## API Surface

FastAPI entry point:

```bash
uv run uvicorn src.api.main:app --reload
```

Core routes:

```text
GET  /
GET  /workflows/health
GET  /workflows
POST /workflows/finrisk/run
GET  /workflows/{run_id}
GET  /workflows/{run_id}/report
GET  /workflows/{run_id}/trace
GET  /workflows/{run_id}/graph
GET  /workflows/{run_id}/evaluation
GET  /workflows/{run_id}/artifacts
GET  /workflows/{run_id}/llm_log
GET  /workflows/{run_id}/chunks
GET  /workflows/{run_id}/sections
GET  /workflows/{run_id}/lifecycles

GET  /supply-chain
POST /supply-chain/explore
POST /supply-chain/expand
GET  /supply-chain/{run_id}
GET  /supply-chain/{run_id}/sankey

GET  /agent-runs
POST /agent-runs
GET  /agent-runs/{run_id}
GET  /agent-runs/{run_id}/timeline
GET  /agent-runs/{run_id}/trace.json
POST /agent-runs/{run_id}/review-items/{item_id}
POST /agent-runs/{run_id}/evidence-candidates/{candidate_id}

GET  /research/financials/{ticker}
GET  /research/management/{ticker}
POST /research/valuation/scenarios
POST /research/valuation/sensitivity
POST /research/valuation/multiple
POST /research/valuation/dcf
GET  /research/valuation/history/{ticker}
POST /research/runs
GET  /research/snapshots
GET  /research/changes/{ticker}
GET/POST /research/expectations
GET/POST /research/alerts
GET/POST /research/peer-groups
POST /research/peer-groups/{peer_group_id}/candidates
POST /research/peer-groups/{peer_group_id}/analysis
POST /research/monitor/scan
GET/POST /research/theses
GET/PUT  /research/watchlist
GET      /research/reminders
```

By default, API routes require `X-API-Key` via `FINRISK_API_KEYS`. For local development only, set `AUTH_DISABLED=1`.

## Architecture

```text
src/
├── agents/            # planner, global runtime, tool-driven agent state
├── api/               # FastAPI routes, auth, rate limit, run stores
├── browser/           # Playwright and agent-browser exploration backends
├── data/              # SEC, EDGAR, transcripts, XBRL, ticker resolution
├── evaluation/        # quality layer, validators, grounding, safety checks
├── evidence/          # evidence candidate normalization
├── graph/             # Neo4j-compatible graph clients, queries, writers
├── graph_reasoning/   # path retrieval, scoring, binding, validation
├── llm/               # OpenAI-compatible clients and tool-loop runtime
├── memory/            # evidence/graph memory and context guardrails
├── reports/           # report models and markdown renderer
├── research/          # snapshots, journal, peers, valuation, monitoring
├── supply_chain/      # product supply-chain workflow and Sankey payloads
├── tools/             # web/search/data/graph tool catalog
└── workflows/         # FinRisk workflow state, steps, quality-gated runner

frontend/
├── src/App.tsx
├── src/staticDemo.ts
└── src/components/

docs/
tests/
```

## Local LLM and Providers

The LLM layer is OpenAI-compatible across local and hosted providers. In practice, most code paths vary only by `base_url`, API key, model, and tool-calling support.

| Provider | `LLM_PROVIDER` | Base URL | Auth env var | Example model |
|---|---|---|---|---|
| SGLang | `sglang` | `http://localhost:30000/v1` | `SGLANG_API_KEY` | `Qwen/Qwen3.5-35B-A3B` |
| vLLM | `vllm` | `http://localhost:8000/v1` | `VLLM_API_KEY` | `Qwen/Qwen3.5-35B-A3B` |
| OpenAI | `openai` | `https://api.openai.com/v1` | `OPENAI_API_KEY` | `gpt-4o-mini` |
| DeepSeek | `deepseek` | `https://api.deepseek.com` | `DEEPSEEK_API_KEY` | `deepseek-v4-flash` |

Local stack:

```bash
docker compose up -d
```

For public APIs, copy `.env.example` to `.env` and fill only the providers you intend to use. Demo and CI paths are designed not to require real API keys.

## Evidence Acquisition

Preferred order:

```text
1. Offline fixture / cached evidence
2. SearchRouter / structured search
3. Browser exploration
```

Supported search providers include:

```text
duckduckgo
brave
tavily
searxng
```

`TAVILY_API_KEY`, `BRAVE_API_KEY`, and `BRAVE_SEARCH_API_KEY` are optional. Missing providers are skipped or downgraded through the router.

## Capability Progress

The canonical status is maintained in the [v0.1 project status](docs/STATUS.md). The current summary is:

- **Completed**: quality-gated FinRisk workflow and the point-in-time personal research cycle.
- **Core complete**: evidence/data foundation, graph and supply-chain research, financial facts, peer analysis, valuation, monitoring, and deployment paths.
- **In progress**: long-horizon context/memory quality, resilient unattended agent execution, full-repository lint cleanup, and release integration.
- **Product redesign complete on its branch**: the ten-route Today/Company/Runs/Journal workbench passed desktop/mobile QA, frontend tests, and production build; it is still one commit ahead of `main`.
- **Unreleased v0.1 candidate**: the repository has no product tag. A code candidate must not be described as a released `v0.1.0`.

Current documentation:

- [Documentation hub](docs/README.md)
- [v0.1 status](docs/STATUS.md)
- [Roadmap](docs/ROADMAP.md)
- [Architecture](docs/ARCHITECTURE.md)
- [v0.1 specification](docs/specs/v0.1.md)
- [Financial reconciliation](docs/validation/financial-reconciliation.md)
- [Frontend acceptance](docs/validation/frontend-acceptance.md)
- [Research Journal local-LLM acceptance](docs/validation/research-journal-live.md)

## Testing

Backend:

```bash
uv run pytest -q
```

Frontend:

```bash
cd frontend
npm test
npm run build

# Isolated Research Journal + local LLM acceptance
cd ..
uv run python scripts/research_journal_live_acceptance.py
```

Latest local verification on 2026-07-25: `972 passed, 7 skipped` on the backend; 18 frontend test files with 76 passing tests; production build passed. The latest recorded three-viewport Chromium, real-mode vLLM, 30/30 guardrail, and zero-vulnerability npm audit evidence is dated 2026-07-12.

Focused checks used during recent development include:

```bash
uv run pytest tests/api tests/workflows tests/evaluation tests/graph_reasoning -q
uv run pytest tests/supply_chain tests/graph tests/tools tests/agents -q
uv run ruff check src/workflows src/evaluation src/graph_reasoning src/reports src/api src/supply_chain src/graph
```

## Roadmap

The immediate v0.1 release path is to merge the product-redesign branch into `main`, re-run CI, npm audit, and browser smoke on that merge candidate, and explicitly choose whether to create the first `v0.1.0` tag.

v0.2 focuses on Agent memory, recovery, idempotency, integration coverage, and lint governance. v0.3 adds segment, consensus, FX, and industry depth; v0.4 covers external notifications and long-horizon calibration. See the [versioned roadmap](docs/ROADMAP.md).

## Non-Goals

- No direct investment advice.
- No buy/sell recommendations.
- No LLM-only confirmed graph edges.
- No requirement for GPU, API keys, live browser success, or live Neo4j in demo mode.
- No generic chatbot UI as the primary interface.

## License

This project includes data from Yahoo Finance, licensed under ODC-BY.
