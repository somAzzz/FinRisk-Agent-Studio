"""Golden-case tests for V21 LLM-driven agent acceptance."""

from __future__ import annotations

from pathlib import Path

from src.evaluation.agent_eval import evaluate_agent_golden_case, load_agent_golden_case

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "agent_golden_cases"


def test_agent_golden_cases_pass_acceptance_harness() -> None:
    results = [
        evaluate_agent_golden_case(load_agent_golden_case(path))
        for path in sorted(FIXTURE_DIR.glob("*.json"))
    ]

    assert results
    assert all(result.final_verdict == "pass" for result in results), results


def test_agent_golden_case_flags_safety_boundary_violation() -> None:
    case = load_agent_golden_case(FIXTURE_DIR / "finrisk_apple_supply_chain.json")
    case.tool_events[0]["arguments"] = {"raw Cypher": "MATCH (n) DETACH DELETE n"}

    result = evaluate_agent_golden_case(case)

    assert result.final_verdict == "fail"
    assert not result.safety_boundary_pass
