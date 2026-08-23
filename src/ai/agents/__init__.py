"""Domain-specific Pydantic AI agents."""

from src.ai.agents.research import (
    ResearchAgentOutput,
    ResearchEvidence,
    build_market_research_agent,
)
from src.ai.agents.structured import (
    FilingRiskExtractionOutput,
    GraphInterpretationOutput,
    ReportGenerationOutput,
    SupplierRelationBatch,
    build_filing_extraction_agent,
    build_generic_extraction_agent,
    build_graph_interpretation_agent,
    build_planner_agent,
    build_relation_extraction_agent,
    build_report_generation_agent,
)

__all__ = [
    "FilingRiskExtractionOutput",
    "GraphInterpretationOutput",
    "ReportGenerationOutput",
    "ResearchAgentOutput",
    "ResearchEvidence",
    "SupplierRelationBatch",
    "build_filing_extraction_agent",
    "build_generic_extraction_agent",
    "build_graph_interpretation_agent",
    "build_market_research_agent",
    "build_planner_agent",
    "build_relation_extraction_agent",
    "build_report_generation_agent",
]
