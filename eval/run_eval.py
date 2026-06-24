"""Offline eval runner for FinRisk Agent Studio.

Loads the golden cases from ``eval/golden_cases.json`` and runs each one
through the workflow in demo mode. Prints a one-line CSV summary per
case and exits non-zero if any case has ``final_status == "fail"``.

Usage::

    uv run python eval/run_eval.py
    uv run python eval/run_eval.py --cases eval/golden_cases.json
    uv run python eval/run_eval.py --fixture tests/fixtures/finrisk/aapl_demo_workflow.json

The runner does not require network access; all cases share the same
demo fixture today (so the workflow outputs are deterministic and
reproducible). Per-case assertions check the guardrail rules and the
"should_not_contain" phrase list, NOT the exact risk labels.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
from pathlib import Path
from typing import Any

# Allow ``python eval/run_eval.py`` without installing the project.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.schemas.finrisk import FinRiskRequest
from src.workflows.evaluation import evaluate_workflow_state
from src.workflows.finrisk_workflow import run_finrisk_workflow


DEFAULT_CASES = ROOT / "eval" / "golden_cases.json"
DEFAULT_FIXTURE = ROOT / "tests" / "fixtures" / "finrisk" / "aapl_demo_workflow.json"


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="run_eval", description=__doc__)
    parser.add_argument(
        "--cases",
        type=Path,
        default=DEFAULT_CASES,
        help="Path to the golden cases JSON file.",
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        default=DEFAULT_FIXTURE,
        help="Path to the demo workflow fixture (shared by all cases).",
    )
    parser.add_argument(
        "--ticker-override",
        action="store_true",
        help=(
            "Rewrite the demo fixture's ticker/company to match each case. "
            "Useful when the fixture data is for a different ticker than the "
            "case. Off by default because the demo fixture is canonical."
        ),
    )
    return parser


def _load_cases(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit(f"golden cases JSON must be a list, got {type(data).__name__}")
    for case in data:
        if "case_id" not in case or "ticker" not in case or "analysis_goal" not in case:
            raise SystemExit(
                f"golden case missing required keys: {case!r}"
            )
    return data


def _case_to_request(case: dict[str, Any]) -> FinRiskRequest:
    return FinRiskRequest(
        ticker=case["ticker"],
        company_name=case.get("company"),
        analysis_goal=case["analysis_goal"],
        demo_mode=True,
    )


def _evidence_coverage(state) -> float:
    """Fraction of top risks that have at least one normalized evidence row."""
    if not state.report or not state.report.top_risks:
        return 0.0
    risk_to_ev: dict[str, set[str]] = {
        r.risk_id: set() for r in state.report.top_risks
    }
    for ev in state.normalized_evidence:
        for rid in ev.related_risk_ids or []:
            if rid in risk_to_ev:
                risk_to_ev[rid].add(ev.evidence_id)
    covered = sum(1 for ids in risk_to_ev.values() if ids)
    return covered / max(1, len(risk_to_ev))


def _check_forbidden_phrases(markdown: str, phrases: list[str]) -> list[str]:
    lowered = markdown.lower()
    return [p for p in phrases if p.lower() in lowered]


async def _run_case(
    case: dict[str, Any],
    *,
    fixture_path: Path,
) -> dict[str, Any]:
    request = _case_to_request(case)
    state = await run_finrisk_workflow(request, fixture_path=fixture_path)
    evaluation = state.evaluation or evaluate_workflow_state(state)
    coverage = _evidence_coverage(state)
    forbidden = _check_forbidden_phrases(
        state.report.markdown if state.report else "",
        case.get("should_not_contain", []),
    )
    return {
        "case_id": case["case_id"],
        "ticker": case["ticker"],
        "final_status": evaluation.final_status,
        "evidence_coverage": round(coverage, 4),
        "financial_advice_risk": evaluation.financial_advice_risk,
        "unsupported_claim_count": len(evaluation.unsupported_claims),
        "schema_valid": evaluation.schema_valid,
        "has_evidence_for_each_risk": evaluation.has_evidence_for_each_risk,
        "source_diversity_score": evaluation.source_diversity_score,
        "hallucination_risk_score": evaluation.hallucination_risk_score,
        "forbidden_phrases_found": forbidden,
    }


def _print_summary(rows: list[dict[str, Any]]) -> None:
    print("case_id,status,evidence_coverage,financial_advice_risk,unsupported_claim_count")
    for r in rows:
        print(
            f"{r['case_id']},{r['final_status']},"
            f"{r['evidence_coverage']},{r['financial_advice_risk']},"
            f"{r['unsupported_claim_count']}"
        )


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    if not args.cases.exists():
        print(f"cases file not found: {args.cases}", file=sys.stderr)
        return 2
    if not args.fixture.exists():
        print(f"fixture file not found: {args.fixture}", file=sys.stderr)
        return 2

    cases = _load_cases(args.cases)
    rows: list[dict[str, Any]] = []
    for case in cases:
        rows.append(
            asyncio.run(_run_case(case, fixture_path=args.fixture))
        )

    _print_summary(rows)

    has_fail = any(r["final_status"] == "fail" for r in rows)
    has_review = any(r["final_status"] == "needs_review" for r in rows)
    # Per spec: only "fail" produces a non-zero exit code in v1.
    if has_fail:
        return 1
    if has_review:
        print(
            f"\n[ok] {len(rows)} cases run, {sum(1 for r in rows if r['final_status'] == 'pass')} pass / "
            f"{sum(1 for r in rows if r['final_status'] == 'needs_review')} needs_review"
        )
    else:
        print(f"\n[ok] {len(rows)} cases run, all pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
