"""Evaluation utilities for the FinText-LLM MVP.

Re-exports the public API of the evaluation submodules so callers can do::

    from src.evaluation import (
        ExtractionEvalResult,
        evaluate_extraction,
        GraphEvalResult,
        evaluate_graph,
        ReportEvalResult,
        evaluate_report,
    )
"""

from src.evaluation.extraction_eval import (
    ExtractionEvalResult,
    evaluate_extraction,
)
from src.evaluation.graph_eval import GraphEvalResult, evaluate_graph
from src.evaluation.report_eval import (
    FORBIDDEN_PHRASES,
    ReportEvalResult,
    evaluate_report,
)

__all__ = [
    "ExtractionEvalResult",
    "FORBIDDEN_PHRASES",
    "GraphEvalResult",
    "ReportEvalResult",
    "evaluate_extraction",
    "evaluate_graph",
    "evaluate_report",
]
