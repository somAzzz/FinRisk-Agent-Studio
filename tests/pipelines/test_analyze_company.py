"""End-to-end tests for the ``analyze_company`` MVP pipeline.

The tests intentionally exercise the ``offline_fixtures=True`` path so
that no external network, API key, or Neo4j instance is required.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.pipelines.analyze_company import (
    AnalyzeCompanyArgs,
    analyze_company,
)


def _args(**overrides) -> AnalyzeCompanyArgs:
    """Return a default ``AnalyzeCompanyArgs`` for the demo run."""
    base: dict = {
        "ticker": "DEMO",
        "offline_fixtures": True,
    }
    base.update(overrides)
    return AnalyzeCompanyArgs.model_validate(base)


def test_offline_demo_produces_non_empty_report() -> None:
    args = _args()
    report = analyze_company(args)
    assert isinstance(report, str)
    assert report.strip()
    # The canonical section heading must appear.
    assert "# Company Research Brief: DEMO" in report


def test_report_contains_disclaimer_and_investment_advice() -> None:
    args = _args()
    report = analyze_company(args)
    assert "Disclaimer" in report
    assert "investment advice" in report


def test_output_path_is_created_when_set(tmp_path: Path) -> None:
    output_path = tmp_path / "reports" / "demo.md"
    args = _args(output=str(output_path))
    report = analyze_company(args)
    assert output_path.exists()
    body = output_path.read_text(encoding="utf-8")
    assert body == report
    assert body.strip()


def test_no_transcripts_flag_is_accepted() -> None:
    args = _args(no_transcripts=True)
    report = analyze_company(args)
    assert "Disclaimer" in report


def test_no_web_flag_is_accepted() -> None:
    args = _args(no_web=True)
    report = analyze_company(args)
    assert "Disclaimer" in report


def test_missing_providers_are_non_fatal(monkeypatch) -> None:
    """Live mode must not crash when no providers or API keys exist.

    The pipeline is expected to degrade gracefully to an empty evidence
    set and still produce a (mostly empty) report.
    """
    import src.pipelines.analyze_company as mod

    def _boom(*_args, **_kwargs):  # noqa: ANN001
        raise RuntimeError("simulated provider failure")

    monkeypatch.setattr(mod, "_load_filings_live", _boom)
    monkeypatch.setattr(mod, "_load_transcripts_live", _boom)
    monkeypatch.setattr(mod, "_load_web_evidence_live", _boom)

    args = AnalyzeCompanyArgs.model_validate(
        {"ticker": "DEMO", "offline_fixtures": False}
    )
    # Even with every fetcher blowing up, the function must return a
    # string (not raise). The report may be short but must not error.
    report = analyze_company(args)
    assert isinstance(report, str)
    assert "Disclaimer" in report


def test_argparse_validation_rejects_bad_year() -> None:
    """Extra fields are rejected by ``AnalyzeCompanyArgs``."""
    with pytest.raises(Exception):
        AnalyzeCompanyArgs.model_validate(
            {"ticker": "DEMO", "year": "not-a-year"}
        )
