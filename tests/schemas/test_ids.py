"""Tests for the stable_id helper."""

from __future__ import annotations

from src.schemas.ids import stable_id


class TestStableId:
    def test_same_inputs_produce_same_output(self) -> None:
        first = stable_id("ev", "sec_filing", "0000320193-23-000106", "Risk Factors")
        second = stable_id("ev", "sec_filing", "0000320193-23-000106", "Risk Factors")
        assert first == second

    def test_different_inputs_produce_different_output(self) -> None:
        first = stable_id("ev", "sec_filing", "0000320193-23-000106")
        second = stable_id("ev", "sec_filing", "0000320193-24-000001")
        assert first != second

    def test_prefix_is_preserved(self) -> None:
        evidence_id = stable_id("ev", "transcript", "AAPL-Q4-2023")
        entity_id = stable_id("ent", "company", "Apple Inc.")
        relation_id = stable_id("rel", "supplies_to", "AAPL", "TSMC")

        assert evidence_id.startswith("ev_")
        assert entity_id.startswith("ent_")
        assert relation_id.startswith("rel_")

    def test_suffix_has_expected_length(self) -> None:
        identifier = stable_id("claim", "risk", "supply chain")
        prefix, _, suffix = identifier.partition("_")
        assert prefix == "claim"
        assert len(suffix) == 12

    def test_order_of_parts_matters(self) -> None:
        first = stable_id("ev", "a", "b")
        second = stable_id("ev", "b", "a")
        assert first != second

    def test_extra_part_changes_output(self) -> None:
        first = stable_id("ev", "transcript", "AAPL")
        second = stable_id("ev", "transcript", "AAPL", "turn-7")
        assert first != second
