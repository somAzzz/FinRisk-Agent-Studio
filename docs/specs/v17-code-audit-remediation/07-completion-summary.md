# V17 Code-Audit Remediation — Completion Summary

This document records the v17 acceptance run performed against
``docs/specs/v17-code-audit-remediation/06-v17-acceptance-checklist.md``.

## Phase 1: V16 data-flow integrity

| Command | Result |
|---|---|
| `uv run pytest tests/workflows/test_v16_quality_gated_orchestrator.py -q` | 7 passed |
| `uv run pytest tests/api/test_quality_graph_api.py tests/api/test_v16_payload_contract.py -q` | 14 passed |
| `uv run pytest tests/graph_reasoning/test_graph_reasoner_step.py -q` | 2 passed |

Status: ✅ **Quality Layer is the runtime gate, not post-hoc.**
Every step produces a `StepEvaluation`; critical-step blockers abort the
workflow; `/graph` returns the v16 `EvidenceGraphPayload`.

## Phase 2: V16 schema / report main path

| Command | Result |
|---|---|
| `uv run pytest tests/schemas/test_finrisk_v16_state.py -q` | 11 passed |
| `uv run pytest tests/workflows/test_risk_scoring.py tests/reports/test_report_renderer.py tests/api/test_workflow_api.py -q` | 20 passed |

Status: ✅ **V16 state fields carry typed Pydantic models.**
`RiskScorerStep` produces `state.risk_scores_v16`; `ReportGeneratorStep`
produces `state.report_v16`; markdown comes from the renderer.

## Phase 3: Graph backend / real mode / safety

| Command | Result |
|---|---|
| `uv run pytest tests/graph_reasoning/test_backends.py tests/graph_reasoning/test_path_interpreter_safety.py -q` | 12 passed |
| `uv run pytest tests/workflows/test_real_mode_fallbacks.py -q` | 6 passed |

Status: ✅ **`GraphPathBackend` protocol + `FixtureGraphBackend` +
`Neo4jGraphBackend` are wired.** Path interpreter scrubs the
financial-advice blocklist; real-mode failures become
`FallbackEvent` rows on the state.

## Phase 4: Ruff + regression gates

| Command | Result |
|---|---|
| `uv run ruff check src/workflows src/evaluation src/graph_reasoning src/reports src/api` | All checks passed |
| `cd frontend && npm test -- --run` | 27 passed |
| `cd frontend && npm run build` | Built successfully |
| `uv run python -m src.workflows.finrisk_workflow --ticker AAPL --analysis-goal "..." --demo-mode` | completed steps: 8 |

## Full-suite result

```text
uv run pytest -q                       → 562 passed, 7 skipped
uv run ruff check ...                  → All checks passed
cd frontend && npm test -- --run       → 27 passed
cd frontend && npm run build           → Built successfully
CLI demo smoke                          → completed
```

## Definition of done (Spec 06 §完成定义)

| Item | Status |
|---|---|
| Quality Layer is runtime gate, not post-hoc only | ✅ |
| Graph payload is V16 typed | ✅ |
| V16 state fields are strongly typed where practical | ✅ (runtime contract pinned by `tests/schemas/test_finrisk_v16_state.py`) |
| `RiskScoreV16` / `RiskReportV16` are primary paths | ✅ |
| Graph narrative is hypothesis-safe | ✅ |
| Fixture and Neo4j graph backends have tests | ✅ |
| Real mode failures are explicit fallback events | ✅ |
| Core ruff gate passes | ✅ |
| Backend and frontend regression tests pass | ✅ |

V17 is complete. V18 (`Product Supply Chain Explorer`) can now reuse
the v17 quality gate, graph payload contract, report/evidence
validation, and ruff/pytest/frontend gates.
