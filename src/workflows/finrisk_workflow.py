"""FinRisk Agent Studio workflow orchestrator + CLI entry point.

The orchestrator runs the eight steps in order and updates
``FinRiskWorkflowState`` between each. The state itself is the only
mutable object passed between steps; the orchestrator never reads loose
dicts.

v16 quality-gated mode
----------------------

When ``quality_gated=True`` and a ``quality_engine`` is supplied, the
orchestrator wraps every step in
:func:`src.workflows.quality_gate.run_step_with_quality_gate`. Each
step then produces a pre- and post-step :class:`StepEvaluation` that
is appended to ``state.evaluations``. The orchestrator applies the
following blocker policy:

- critical step (company_resolver, filing_risk_extractor,
  evidence_normalizer, risk_scorer, report_generator, evaluator)
  → state.status = "failed" on any BLOCKER finding.
- non-critical step (market_explorer, graph_reasoner)
  → state.status = "needs_review" on any BLOCKER finding;
  the workflow continues to the next step.

The CLI is the canonical demo entry point:

    uv run python -m src.workflows.finrisk_workflow \\
        --ticker AAPL \\
        --analysis-goal "Identify macro, policy and supply-chain risks." \\
        --demo-mode
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import uuid
from pathlib import Path
from typing import Any

from src.workflows.state import (
    FinRiskRequest,
    FinRiskWorkflowState,
    WorkflowTraceEvent,
    utcnow,
)
from src.workflows.steps.company_resolver import CompanyResolverStep
from src.workflows.steps.evaluator import EvaluatorStep
from src.workflows.steps.evidence_normalizer import EvidenceNormalizerStep
from src.workflows.steps.filing_risk_extractor import FilingRiskExtractorStep
from src.workflows.steps.graph_reasoner import GraphReasonerStep
from src.workflows.steps.market_explorer_step import MarketExplorerStep
from src.workflows.steps.report_generator import ReportGeneratorStep
from src.workflows.steps.risk_scorer import RiskScorerStep

logger = logging.getLogger(__name__)

DEFAULT_FIXTURE_DIR = Path("tests/fixtures/finrisk")


# Steps whose failure must abort the workflow. Non-critical steps
# (market_explorer, graph_reasoner) fall back gracefully and mark
# the workflow as ``needs_review``.
_CRITICAL_STEPS: frozenset[str] = frozenset(
    {
        "company_resolver",
        "filing_risk_extractor",
        "evidence_normalizer",
        "risk_scorer",
        "report_generator",
        "evaluator",
    }
)


def _build_default_steps(fixture_path: Path):
    """Wire the production step pipeline.

    Order is fixed by the spec and must not be reordered lightly.
    """
    return [
        CompanyResolverStep(fixture_path=fixture_path),
        FilingRiskExtractorStep(fixture_path=fixture_path),
        MarketExplorerStep(fixture_path=fixture_path),
        EvidenceNormalizerStep(),
        RiskScorerStep(),
        GraphReasonerStep(fixture_path=fixture_path),
        ReportGeneratorStep(),
        EvaluatorStep(),
    ]


def _has_blocker(state: FinRiskWorkflowState) -> bool:
    """Return ``True`` if the latest :class:`StepEvaluation` is a blocker."""
    if not state.evaluations:
        return False
    from src.evaluation.models import GuardrailSeverity

    last = state.evaluations[-1]
    return any(
        f.severity == GuardrailSeverity.BLOCKER for f in last.findings
    )


async def run_finrisk_workflow(
    request: FinRiskRequest,
    *,
    fixture_path: Path | None = None,
    steps=None,
    run_id: str | None = None,
    initial_state: FinRiskWorkflowState | None = None,
    quality_engine: Any | None = None,
    quality_gated: bool = False,
) -> FinRiskWorkflowState:
    """Execute the workflow end-to-end and return the final state.

    Args:
        request: The user-facing request.
        fixture_path: Optional path to the demo JSON fixture.
        steps: Optional list of pre-built step instances (mainly for tests).
        run_id: Optional run identifier to reuse. When provided, the
            orchestrator starts the state with this id instead of
            generating a new one. Useful when the API layer has already
            created a state and wants the workflow to fill it in.
        initial_state: Optional pre-built state to mutate. When given,
            the orchestrator reuses this object (and its run_id)
            instead of building a fresh one. ``request`` is still
            required so CLI callers can construct one.
        quality_engine: Optional :class:`GuardrailEngine` that runs
            pre/post-step validation when ``quality_gated`` is true.
        quality_gated: When true, each step is wrapped in
            :func:`run_step_with_quality_gate`. The default ``False``
            keeps the v15 behaviour so existing tests are not
            affected.
    """
    fixture_path = fixture_path or DEFAULT_FIXTURE_DIR / "aapl_demo_workflow.json"
    if initial_state is not None:
        state = initial_state
    else:
        state = FinRiskWorkflowState(
            run_id=run_id or f"run-{uuid.uuid4().hex[:12]}",
            request=request,
        )
    state.status = "running"
    steps = steps or _build_default_steps(fixture_path)

    if quality_gated and quality_engine is None:
        raise ValueError(
            "quality_gated=True requires a non-None quality_engine"
        )

    for step in steps:
        if state.status == "failed":
            # Mark remaining steps as skipped.
            state.trace.append(
                WorkflowTraceEvent(
                    step_name=step.name,
                    status="skipped",
                    started_at=utcnow(),
                    completed_at=utcnow(),
                    error="workflow aborted by earlier failure",
                )
            )
            continue

        if quality_gated and quality_engine is not None:
            from src.workflows.quality_gate import run_step_with_quality_gate

            state = await run_step_with_quality_gate(
                state,
                step=step,
                engine=quality_engine,
            )
            if _has_blocker(state):
                if step.name in _CRITICAL_STEPS:
                    state.status = "failed"
                    logger.warning(
                        "critical step %s produced a BLOCKER; aborting",
                        step.name,
                    )
                else:
                    state.status = "needs_review"
                    logger.info(
                        "non-critical step %s produced a BLOCKER; "
                        "continuing with needs_review",
                        step.name,
                    )
                    state.status = "running"  # keep going
        else:
            state = await step(state)

    return state


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="finrisk_workflow",
        description="FinRisk Agent Studio workflow runner.",
    )
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--company-name", default=None)
    parser.add_argument("--analysis-goal", required=True)
    parser.add_argument("--time-horizon", default="6-12 months")
    parser.add_argument("--year", type=int, default=None)
    parser.add_argument(
        "--sources",
        nargs="*",
        default=None,
        help="Space-separated list: filing web transcript graph",
    )
    parser.add_argument("--max-browser-steps", type=int, default=5)
    parser.add_argument("--demo-mode", action="store_true")
    parser.add_argument("--cached-mode", action="store_true")
    parser.add_argument("--fixture-path", default=None)
    parser.add_argument(
        "--output",
        default=None,
        help="Optional path to write the JSON state and Markdown report.",
    )
    return parser


def _parse_sources(values: list[str] | None) -> list[str] | None:
    if not values:
        return None
    allowed = {"filing", "web", "transcript", "graph"}
    bad = [v for v in values if v not in allowed]
    if bad:
        msg = f"invalid sources: {bad}; allowed: {sorted(allowed)}"
        raise SystemExit(msg)
    return values


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    request = FinRiskRequest(
        ticker=args.ticker,
        company_name=args.company_name,
        analysis_goal=args.analysis_goal,
        time_horizon=args.time_horizon,
        year=args.year,
        sources=_parse_sources(args.sources)
        or ["filing", "web", "graph"],
        max_browser_steps=args.max_browser_steps,
        demo_mode=args.demo_mode,
        cached_mode=args.cached_mode,
    )
    fixture_path = (
        Path(args.fixture_path) if args.fixture_path else None
    )

    state = asyncio.run(
        run_finrisk_workflow(request, fixture_path=fixture_path)
    )

    # Persist outputs if requested.
    if args.output:
        out_dir = Path(args.output).parent
        out_dir.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(
            state.model_dump_json(indent=2), encoding="utf-8"
        )
        if state.report is not None:
            md_path = Path(args.output).with_suffix(".md")
            md_path.write_text(state.report.markdown, encoding="utf-8")

    # CLI summary
    print(f"run_id: {state.run_id}")
    print(f"status: {state.status}")
    print(f"completed steps: {len([e for e in state.trace if e.status == 'completed'])}")
    if state.report is not None:
        print(f"top risks: {len(state.report.top_risks)}")
        print(f"evidence rows: {len(state.report.evidence_table)}")
        print(f"graph insights: {len(state.report.graph_insights)}")
        print("--- report preview ---")
        print(state.report.markdown[:1200])
    if state.evaluation is not None:
        print("--- evaluation ---")
        print(f"final_status: {state.evaluation.final_status}")
        print(f"schema_valid: {state.evaluation.schema_valid}")
        print(f"has_evidence_for_each_risk: {state.evaluation.has_evidence_for_each_risk}")
        print(f"financial_advice_risk: {state.evaluation.financial_advice_risk}")
        print(
            f"source_diversity_score: {state.evaluation.source_diversity_score}"
        )
        print(
            f"hallucination_risk_score: {state.evaluation.hallucination_risk_score}"
        )
    print("--- trace ---")
    for event in state.trace:
        print(
            f"- {event.step_name}: {event.status} "
            f"({event.started_at.isoformat()})"
            + (f" error={event.error}" if event.error else "")
        )

    return 0 if state.status in {"completed", "needs_review"} else 1


if __name__ == "__main__":
    sys.exit(main())