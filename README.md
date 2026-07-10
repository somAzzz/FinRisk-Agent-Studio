# FinRisk Agent Studio

Evidence-first agent workflow for SEC filing analysis, market evidence collection, graph reasoning, product supply-chain exploration, runtime quality guardrails, and human review.

FinRisk Agent Studio is an open-source reference implementation for financial research workflows. It is not a generic "chat with filings" demo. The project focuses on auditable agent execution: structured inputs, tool traces, evidence candidates, deterministic scoring, graph paths, quality gates, and reviewable outputs.

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
npm install
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

The Vite dev server proxies `/workflows`, `/supply-chain`, and `/agent-runs` to the FastAPI backend.

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

Implementation history is grouped by capability rather than presented as product releases:

- **Risk Studio remediation completed**: quality layer became a runtime gate; graph payloads, report models, scoring, and safety checks were pinned by tests.
- **Supply-chain explorer completed and hardened**: Sankey model, recursive expansion, real SearchRouter path, graph writer, observability, and frontend integration.
- **Context guardrail layer started**: memory adapters, ingestion, graph-edge memory, and memory write guardrails are in place.
- **Tool loop implemented**: provider-neutral tool catalog, OpenAI-compatible tool loop, budget controls, data tools, and JSON fallback.
- **Agent runtime in progress**: `/agent-runs` API, global runtime, evidence candidates, review gates, redacted trace download, and frontend trace UI.
- **Local E2E validated**: recorded runs show real FinRisk, supply-chain, and agent-run flows through local SGLang, FastAPI, Vite, and Neo4j-compatible paths.
- **GitHub Pages published**: static dashboard is live at the project URL above.

Recorded validation reports:

- [Documentation hub](docs/README.md)
- [Current analyst-workbench roadmap](docs/current/analyst-workbench-roadmap.md)
- [Risk Studio remediation summary](docs/specs/v17-code-audit-remediation/07-completion-summary.md)
- [Supply-chain explorer completion summary](docs/specs/v18-product-supply-chain-sankey/07-completion-summary.md)
- [Supply-chain production hardening progress](docs/specs/v18-product-supply-chain-sankey/09-production-hardening-progress.md)
- [Local LLM E2E validation](docs/history/reports/validation/local-llm-e2e-api-frontend-2026-06-27.md)
- [Agent system gap audit](docs/history/reports/audits/agent-system-gap-report-2026-06-27.md)

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
```

Focused checks used during recent development include:

```bash
uv run pytest tests/api tests/workflows tests/evaluation tests/graph_reasoning -q
uv run pytest tests/supply_chain tests/graph tests/tools tests/agents -q
uv run ruff check src/workflows src/evaluation src/graph_reasoning src/reports src/api src/supply_chain src/graph
```

## Roadmap

Current priorities are production hardening rather than proving the workflow concept:

1. Add persistent run storage for workflows, supply-chain runs, and agent runs beyond the current in-memory/default local store paths.
2. Complete real Neo4j integration smoke tests for graph write/read, upstream path query, and recursive supply-chain expansion.
3. Replace rule-based supply-chain decomposition and supplier relation extraction with structured LLM/NLI extractors guarded by evidence checks.
4. Tighten provider budget controls: max provider calls, timeout policies, retry budgets, cache TTLs, and cost estimates.
5. Continue hardening browser exploration with stricter timeout, backend-health, and trace metadata.
6. Expand golden-case evaluation for agent runs, evidence candidate quality, and human-review outcomes.
7. Keep the GitHub Pages demo aligned with the local dashboard as frontend features evolve.

## Non-Goals

- No direct investment advice.
- No buy/sell recommendations.
- No LLM-only confirmed graph edges.
- No requirement for GPU, API keys, live browser success, or live Neo4j in demo mode.
- No generic chatbot UI as the primary interface.

## License

This project includes data from Yahoo Finance, licensed under ODC-BY.
