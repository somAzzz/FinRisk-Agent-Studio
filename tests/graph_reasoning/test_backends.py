"""v17 tests for the graph path backends."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.graph_reasoning.backends import (
    FixtureGraphBackend,
    GraphPathBackend,
    Neo4jGraphBackend,
)
from src.graph_reasoning.models import (
    GraphEdge,
    GraphEdgeMetadata,
    GraphNode,
    GraphQueryContext,
)
from src.workflows.state import utcnow


def _context() -> GraphQueryContext:
    return GraphQueryContext(
        company_id="company:AAPL",
        ticker="AAPL",
        risk_ids=[],
        focus_entities=[],
        focus_risk_types=["supply_chain"],
        max_hops=3,
        allowed_edge_types=["DEPENDS_ON", "LOCATED_IN", "EXPOSED_TO", "AFFECTS"],
    )


# ---------------------------------------------------------------------------
# FixtureGraphBackend
# ---------------------------------------------------------------------------


def test_fixture_backend_returns_paths() -> None:
    paths = FixtureGraphBackend().retrieve(_context())
    assert paths
    assert all(p.path_text for p in paths)


def test_fixture_backend_is_a_graph_path_backend() -> None:
    """The Protocol runtime check accepts the fixture backend."""
    backend = FixtureGraphBackend()
    assert isinstance(backend, GraphPathBackend)


def test_fixture_backend_respects_empty_node_set() -> None:
    # A backend with no nodes/edges returns no paths even if the
    # default fixture is non-empty.
    backend = FixtureGraphBackend(nodes=[], edges=[])
    assert backend.retrieve(_context()) == []


# ---------------------------------------------------------------------------
# Neo4jGraphBackend
# ---------------------------------------------------------------------------


def _neo4j_node(
    *, nid: str, label: str, type_: str, props: dict | None = None
) -> MagicMock:
    node = MagicMock()
    node.element_id = nid
    node.id = nid
    node.labels = [type_]
    node.get = lambda key, default=None: (props or {}).get(key, default)
    node.__iter__ = lambda self: iter((props or {}).items())
    return node


def _neo4j_rel(
    *,
    src: MagicMock, dst: MagicMock, type_: str, evidence_ids: list[str], confidence: float
) -> MagicMock:
    rel = MagicMock()
    rel.start_node = src
    rel.end_node = dst
    rel.type = type_
    rel.get = lambda key, default=None: {
        "evidence_ids": evidence_ids,
        "confidence": confidence,
    }.get(key, default)
    return rel


def _neo4j_path() -> MagicMock:
    company = _neo4j_node(
        nid="c1", label="Apple", type_="Company", props={"label": "Apple"}
    )
    supplier = _neo4j_node(
        nid="s1", label="TSMC", type_="Supplier", props={"label": "TSMC"}
    )
    rel = _neo4j_rel(
        src=company, dst=supplier, type_="DEPENDS_ON",
        evidence_ids=["ne-1"], confidence=0.9,
    )
    path = MagicMock()
    path.nodes = [company, supplier]
    path.relationships = [rel]
    return path


def test_neo4j_backend_uses_duck_typed_session() -> None:
    path = _neo4j_path()
    record = MagicMock()
    record.__getitem__ = lambda self, key: path
    session = MagicMock()
    session.run.return_value = [record]
    client = MagicMock()
    client.session.return_value.__enter__.return_value = session

    backend = Neo4jGraphBackend(client)
    paths = backend.retrieve(_context())
    assert len(paths) == 1
    assert paths[0].hop_count == 1
    assert paths[0].evidence_ids == ["ne-1"]


def test_neo4j_backend_handles_session_exception() -> None:
    client = MagicMock()
    client.session.return_value.__enter__.side_effect = RuntimeError("boom")
    backend = Neo4jGraphBackend(client)
    with pytest.raises(RuntimeError):
        backend.retrieve(_context())


def test_subsystem_swallows_backend_exception() -> None:
    """The subsystem converts backend failures into a guardrail finding."""
    from src.graph_reasoning import GraphReasoningSubsystem
    from src.schemas.finrisk import (
        CompanyProfile,
        FinRiskRequest,
        FinRiskWorkflowState,
    )

    class BoomBackend:
        def retrieve(self, context):
            raise RuntimeError("down")

    class BoomSubsystem(GraphReasoningSubsystem):
        def __init__(self) -> None:
            super().__init__(backend=BoomBackend())

    state = FinRiskWorkflowState(
        run_id="r",
        request=FinRiskRequest(
            ticker="AAPL", analysis_goal="x", demo_mode=True
        ),
        company=CompanyProfile(
            company_name="Apple",
            ticker="AAPL",
            cik="0000320193",
            filing_type="10-K",
            analysis_year=2024,
            source="fixture",
            resolved_at=utcnow(),
        ),
    )
    payload = BoomSubsystem().run(state)
    assert payload.guardrail_findings
    assert "down" in payload.guardrail_findings[0]["message"]
