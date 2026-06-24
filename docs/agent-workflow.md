# FinRisk Agent Studio — End-to-End Workflow

This document is the canonical reference for the FinRisk Agent Studio
workflow. It covers the data flow, the eight steps, the API surface,
and the guardrail evaluation. A new developer should be able to run
the full demo after reading this document and
[`demo-script.md`](./demo-script.md).

## 1. Goal

Take a user request (ticker + analysis goal) and produce a typed
risk-intelligence brief that is:

- **Grounded** in SEC filing quotes and recent market evidence.
- **Scored** with a deterministic, auditable formula.
- **Cross-checked** by a graph-based second-order reasoning step.
- **Evaluated** by code-level guardrails that can downgrade or fail
  the report.
- **Exposed** via a small FastAPI surface (run / status / report).

The first version runs entirely in **demo mode** using a single
fixture for AAPL. The same eight-step pipeline runs in **live mode**
when LLM, browser, web-search, and Neo4j are available; the steps
fall back to cached / fixture data when those services are down.

## 2. Input

A `FinRiskRequest` (Pydantic) captures:

| field            | type        | notes                                            |
|------------------|-------------|--------------------------------------------------|
| `ticker`         | str         | uppercased; validated against a known universe.  |
| `company_name`   | str \| None | optional hint for the resolver step.             |
| `analysis_goal`  | str         | non-empty; the user-facing question.             |
| `time_horizon`   | str         | default `"6-12 months"`.                         |
| `year`           | int \| None | fiscal year for filing selection.                |
| `sources`        | list[str]   | subset of `filing`, `web`, `transcript`, `graph`. |
| `max_browser_steps` | int       | cap on browser tool calls (live mode).           |
| `demo_mode`      | bool        | short-circuit all live calls.                    |
| `cached_mode`    | bool        | use caches for live calls when available.        |

## 3. Output

A `FinRiskWorkflowState` flows through the eight steps. The terminal
state carries:

- `report: RiskReport` (Pydantic) with structured sections and a
  pre-rendered markdown body.
- `evaluation: WorkflowEvaluation` (Pydantic) with the guardrail
  verdict.
- `trace: list[WorkflowTraceEvent]` — one row per step, with
  started/completed timestamps and optional error message.
- `status: "completed" | "needs_review" | "failed"`.

## 4. The Eight Steps

| # | Step                | Purpose                                                      | Live fallback                              |
|---|---------------------|--------------------------------------------------------------|--------------------------------------------|
| 1 | `company_resolver`  | Map ticker → `CompanyProfile` (CIK, name, fiscal year).      | fixture override in demo mode              |
| 2 | `filing_risk_extractor` | Pull Item 1A from latest 10-K / 10-Q and extract risks. | fixture override; keyword-tagged fallback  |
| 3 | `market_explorer`   | Collect recent news / market evidence for the ticker.        | `SearchRouter` (cached) or fixture         |
| 4 | `evidence_normalizer` | Dedupe and link `NormalizedEvidence` rows to risks.       | in-memory dedupe by `source_url`           |
| 5 | `risk_scorer`       | Compute `RiskScore.final_score` per risk.                    | deterministic formula                      |
| 6 | `graph_reasoner`    | Emit `GraphInsight` rows for second-order effects.           | `GraphReasoningAgent` or fixture           |
| 7 | `report_generator`  | Render the typed `RiskReport` and markdown.                  | strips forbidden phrases, drops orphans    |
| 8 | `evaluator`         | Compute `WorkflowEvaluation` and `state.status`.             | code-level guardrails (no LLM)             |

### 4.1 Risk Score Formula

```
final_score = 0.35 * base_severity
            + 0.25 * recent_signal_strength
            + 0.20 * evidence_quality
            + 0.10 * source_diversity
            + 0.10 * novelty_score
            (+ optional graph_centrality weighting)
```

All components are in `[0, 1]` except `base_severity` (1–5, normalized
to `[0, 1]`). The formula is implemented in
`src/workflows/steps/risk_scorer.py::compute_risk_score`.

### 4.2 Graph Insight ID Translation

`GraphInsight.supporting_evidence_ids` references **normalized**
evidence ids (`ne-...`). The graph step translates raw risk_ids and
market `evidence_id`s into the `ne-...` space so the report and the
guardrail checker reference the same evidence table.

## 5. Demo Mode Data

The demo fixture lives at
`tests/fixtures/finrisk/aapl_demo_workflow.json`. It contains:

- 4 filing risks (supply_chain, policy, geopolitical, operational).
- 2 market evidence rows (one supporting, one contradicting).
- 1 graph insight (Taiwan Strait / TSMC).
- 1 company profile (Apple Inc., CIK 0000320193).

This satisfies the spec's "≥ 3 filing risks, ≥ 5 evidence, ≥ 2 source
types, ≥ 1 supply-chain/geopolitical insight, ≥ 1 policy/regulatory
risk" requirements.

## 6. API

The FastAPI surface lives in `src/api/`. Run with:

```bash
uvicorn src.api.main:app --reload
```

| Method | Path                              | Purpose                         |
|--------|-----------------------------------|---------------------------------|
| GET    | `/`                               | service metadata                |
| GET    | `/workflows/health`               | health + run count              |
| POST   | `/workflows/finrisk/run`          | start a new run (returns 202)   |
| GET    | `/workflows/{run_id}`             | status + timeline               |
| GET    | `/workflows/{run_id}/report`      | final report markdown           |

The store is process-local (`InMemoryRunStore`). Background execution
uses `asyncio.create_task`. Tests can opt out by setting
`FINRISK_SKIP_BACKGROUND=1`.

## 7. Guardrails (Spec 04)

Implemented in `src/workflows/evaluation.py`:

| ID  | Rule                                                       | Failure      |
|-----|------------------------------------------------------------|--------------|
| G1  | report exists and is schema-valid                          | fail         |
| G2  | every top risk has supporting evidence                     | fail         |
| G3  | severity 1–5; score 0–1 (defended at Pydantic)             | fail         |
| G4  | "strong buy", "guaranteed return", "must invest" present   | fail         |
| G4  | "buy now", "sell now", "稳赚", "买入" present              | needs_review |
| G5  | report contains "Evidence vs Inference" section            | needs_review |
| G6  | report contains "Confidence & Limitations" section         | needs_review |
| G7  | `source_diversity_score >= 0.2`                            | needs_review |
| G8  | graph insight references valid evidence ids                | fail         |
| G8  | top_risks count <= risk_scores count                       | needs_review |

The evaluator step (`src/workflows/steps/evaluator.py`) is a thin
wrapper that maps `final_status` to `state.status`.

## 8. Golden Cases & Eval Runner

- `eval/golden_cases.json` — 5 cases (AAPL, NVDA, MSFT, TSLA, XOM).
- `eval/run_eval.py` — runs each case through the demo workflow and
  prints a one-line CSV summary. Exit code is non-zero on `fail`.

## 9. Cached Fallback Matrix

| Service              | Live                     | Cached fallback                |
|----------------------|--------------------------|--------------------------------|
| LLM                  | structured extraction    | fixture filing risks           |
| browser              | `agent-browser`          | `SearchRouter` cache           |
| web search provider  | `SearchRouter`           | fixture market evidence        |
| Neo4j                | `GraphReasoningAgent`    | fixture graph insights         |
| SEC network request  | `SECFilingFetcher`       | fixture filing text            |

The trace records the fallback reason in `WorkflowTraceEvent.error`.

## 10. Testing

```bash
uv run pytest -q                                # full suite
uv run pytest tests/workflows -q                # workflow + guardrails
uv run pytest tests/api -q                     # API smoke
uv run python eval/run_eval.py                 # golden cases
uv run python -m src.workflows.finrisk_workflow --ticker AAPL --demo-mode
```

## 11. Non-Goals (v1)

- No production SEC/transcript/web/Neo4j closure.
- No auth or multi-tenant support.
- No long-term run persistence.
- No trading signals or investment advice (the report explicitly
  disclaims this).
