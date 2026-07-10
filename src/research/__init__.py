"""Company research primitives exposed through cycle-safe lazy imports."""

from __future__ import annotations

from importlib import import_module
from typing import Any

_EXPORTS = {
    "ChangeType": "src.research.models",
    "FinancialChange": "src.research.models",
    "FinancialMetricPoint": "src.research.models",
    "FinancialSnapshot": "src.research.models",
    "FinancialSnapshotBuilder": "src.research.financial_snapshot",
    "ManagementPeriodSnapshot": "src.research.management_snapshot",
    "ManagementComparisonResponse": "src.research.management_snapshot",
    "ManagementSignalChange": "src.research.management_snapshot",
    "ManagementTopicSignal": "src.research.management_snapshot",
    "RiskFinancialImpact": "src.research.risk_impact",
    "build_management_snapshot": "src.research.management_snapshot",
    "compare_management_snapshots": "src.research.management_snapshot",
    "map_risk_financial_impact": "src.research.risk_impact",
    "ScenarioValuationRequest": "src.research.valuation",
    "ScenarioValuationResponse": "src.research.valuation",
    "ScenarioValuationResult": "src.research.valuation",
    "ValuationScenarioInput": "src.research.valuation",
    "calculate_scenario_valuation": "src.research.valuation",
    "Catalyst": "src.research.journal",
    "InvestmentThesis": "src.research.journal",
    "ResearchJournalStore": "src.research.journal",
    "ResearchReminder": "src.research.journal",
    "ThesisReview": "src.research.journal",
    "WatchlistItem": "src.research.journal",
}

__all__ = list(_EXPORTS)


def __getattr__(name: str) -> Any:
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(name)
    value = getattr(import_module(module_name), name)
    globals()[name] = value
    return value
