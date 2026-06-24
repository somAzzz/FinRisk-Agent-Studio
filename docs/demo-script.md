# FinRisk Agent Studio — 5-Minute Demo Script

A guided walkthrough that takes a new viewer from "what is this?" to
"this is a real risk report" in five minutes. Total runtime is under
two minutes of wall-clock time; the rest of the time is for narration.

## Pre-flight (~30 s)

```bash
# 1. Install dependencies (skip if the viewer already ran this).
uv sync

# 2. Run the test suite to show the green bar.
uv run pytest -q
```

The test suite finishes in ~12 s and proves the workflow + API +
guardrails all work without any external service.

## Act 1 — Workflow CLI demo (~1 min)

```bash
uv run python -m src.workflows.finrisk_workflow \
  --ticker AAPL \
  --analysis-goal "Identify macro, policy and supply-chain risks that changed recently." \
  --demo-mode
```

The CLI exits 0 and prints:

- `run_id` (12 hex chars after `run-`).
- `status: completed` (or `needs_review`).
- `completed steps: 8`.
- Top risks + evidence + graph insights.
- A 1200-character preview of the report.

**Talking points**

1. The whole pipeline ran in demo mode (no SEC, no LLM, no Neo4j).
2. Eight steps each left a typed trace event.
3. The deterministic risk-score formula sorted the four filing risks.
4. The report explicitly disclaims "not investment advice".

## Act 2 — Report content (~1 min)

```bash
uv run python -m src.workflows.finrisk_workflow \
  --ticker AAPL \
  --analysis-goal "Identify macro, policy and supply-chain risks that changed recently." \
  --demo-mode \
  --output /tmp/aapl_report.json
```

This writes `state.model_dump_json(...)` to `/tmp/aapl_report.json`
and `/tmp/aapl_report.md`.

Open `/tmp/aapl_report.md` in any editor and walk through the
required sections:

1. **Executive Summary** — score-sorted top risks.
2. **Top Risks** — each with a verbatim filing quote.
3. **Recent Changes** — market evidence rows.
4. **Evidence Table** — one row per `NormalizedEvidence`.
5. **Second-Order Effects** — graph insight (Apple → TSMC → Taiwan
   Strait).
6. **Evidence vs Inference** — separates the three classes.
7. **Confidence & Limitations** — explicit caveats.
8. **Disclaimer** — "not investment advice".

## Act 3 — API surface (~1 min)

```bash
# Terminal 1: start the API
uvicorn src.api.main:app --reload
```

```bash
# Terminal 2: kick off a run
curl -X POST http://127.0.0.1:8000/workflows/finrisk/run \
  -H "Content-Type: application/json" \
  -d '{
    "ticker": "AAPL",
    "analysis_goal": "Identify macro, policy and supply-chain risks that changed recently.",
    "sources": ["filing", "web", "graph"],
    "demo_mode": true
  }'
```

Capture the `run_id` from the response, then poll:

```bash
curl http://127.0.0.1:8000/workflows/$RUN_ID | jq
curl http://127.0.0.1:8000/workflows/$RUN_ID/report | jq '.markdown'
```

**Talking points**

- `POST /workflows/finrisk/run` returns 202 with a `run_id`.
- `GET /workflows/{run_id}` shows the live trace + risk count.
- `GET /workflows/{run_id}/report` returns the markdown body.
- The store is in-memory; restart the server and runs are gone.

## Act 4 — Guardrails & golden cases (~1 min)

```bash
uv run pytest tests/workflows/test_guardrails.py -q
uv run python eval/run_eval.py
```

The first command runs 13 unit tests covering G1–G8. The second runs
5 golden cases (AAPL, NVDA, MSFT, TSLA, XOM) and prints a CSV
summary; all 5 should pass.

**Talking points**

- The evaluator is code-only — no LLM critic in v1.
- Hard fails (G1, G2, G4 strong, G8 missing evidence) flip the
  verdict to `fail`.
- Review issues (G4 soft, G5/G6 missing sections, G7 low diversity,
  G8 orphan risks) flip it to `needs_review`.
- `eval/run_eval.py` exits non-zero only on `fail`, so the demo
  exits 0.

## Act 5 — Failure modes (~30 s)

Quickly demo the guardrails by inserting a forbidden phrase and
re-running:

```python
# In a Python REPL or a one-liner:
python -c "
import asyncio
from src.schemas.finrisk import FinRiskRequest
from src.workflows.finrisk_workflow import run_finrisk_workflow
from pathlib import Path
async def go():
    state = await run_finrisk_workflow(
        FinRiskRequest(ticker='AAPL', analysis_goal='Test', demo_mode=True),
        fixture_path=Path('tests/fixtures/finrisk/aapl_demo_workflow.json'),
    )
    state.report = state.report.model_copy(update={
        'markdown': state.report.markdown.replace('risk factors', 'strong buy')
    })
    from src.workflows.evaluation import evaluate_workflow_state
    print(evaluate_workflow_state(state).final_status)
asyncio.run(go())
"
```

It prints `fail` — the guardrail detected the forbidden phrase and
the workflow would have flagged the report as unsafe.

## Wrap-up

The five-minute demo proves:

1. The full eight-step pipeline runs deterministically in demo mode.
2. The CLI, the API, the eval runner, and the unit tests all agree.
3. The guardrails catch the most obvious failure modes without an
   LLM critic.

For a deeper look, see [`agent-workflow.md`](./agent-workflow.md) and
the spec index at [`specs/00-finrisk-agent-studio-spec-index.md`](./specs/00-finrisk-agent-studio-spec-index.md).
