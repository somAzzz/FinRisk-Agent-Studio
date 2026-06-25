"""Tests for ``src.data.sec_sections.SectionParser``."""

from __future__ import annotations

import json
from pathlib import Path

from src.data.sec_sections import SECTION_PATTERNS, SectionParser


def _10k_text() -> str:
    return (
        "Annual Report\n"
        "\n"
        "Item 1. Business\n"
        "We design and sell demonstration products.\n"
        "Item 1A. Risk Factors\n"
        "We face risks from supply chain disruptions.\n"
        "Item 7. Management's Discussion and Analysis\n"
        "Revenue grew modestly year-over-year.\n"
        "Item 7A. Quantitative and Qualitative Disclosures\n"
        "We use derivatives to manage currency risk.\n"
    )


def test_parser_extracts_canonical_sections() -> None:
    parser = SectionParser()
    sections = parser.parse(_10k_text())
    assert "section_1" in sections
    assert "section_1a" in sections
    assert "section_7" in sections
    assert "section_7a" in sections


def test_parser_preserves_full_text_fallback() -> None:
    parser = SectionParser()
    sections = parser.parse(_10k_text())
    assert sections["full_text"].text == _10k_text().strip()


def test_parser_handles_em_dash_separator() -> None:
    text = "Item 1 — Business\nFoo.\nItem 1A. Risk Factors\nBar."
    sections = SectionParser().parse(text)
    assert "section_1" in sections
    assert "section_1a" in sections


def test_parser_handles_roman_numerals() -> None:
    text = (
        "Item I. Business\nFoo.\n"
        "Item II. Properties\nBar.\n"
        "Item III. Legal Proceedings\nBaz."
    )
    sections = SectionParser().parse(text)
    assert "section_1" in sections
    assert "section_2" in sections
    assert "section_3" in sections


def test_parser_records_char_offsets() -> None:
    sections = SectionParser().parse(_10k_text())
    for name, sec in sections.items():
        if name == "full_text":
            continue
        assert sec.char_start >= 0
        assert sec.char_end > sec.char_start


def test_parser_handles_empty_html() -> None:
    parser = SectionParser()
    sections = parser.parse("")
    assert sections["full_text"].text == ""


def test_parser_handles_html_input() -> None:
    text = (
        "<html><body>"
        "<h2>Item 1. Business</h2><p>Foo.</p>"
        "<h2>Item 1A. Risk Factors</h2><p>Bar.</p>"
        "</body></html>"
    )
    sections = SectionParser().parse(text)
    assert "section_1" in sections
    assert "section_1a" in sections


def test_parser_pattern_dict_has_canonical_keys() -> None:
    for key in (
        "section_1",
        "section_1a",
        "section_2",
        "section_7",
        "section_7a",
    ):
        assert key in SECTION_PATTERNS


# ---------------------------------------------------------------------------
# Tests for the Forward-Looking Statements trap fix (added 2026-06-25)
# ---------------------------------------------------------------------------


def test_parser_handles_nbsp_entity_in_html() -> None:
    """``Item&#160;1A. Risk Factors`` (NBSP entity) must match after
    html.unescape + NBSP normalisation."""
    text = (
        "<html><body>"
        "<h2>Item&#160;1A.&nbsp;Risk Factors</h2>"
        "<p>Supply chain risks are material.</p>"
        "</body></html>"
    )
    sections = SectionParser().parse(text, prefer_substantive_match=True)
    assert "section_1a" in sections
    assert "Supply chain risks" in sections["section_1a"].text


def test_parser_prefers_substantive_match_over_disclaimer() -> None:
    """When an FLS disclaimer mentions 'Item 1A. Risk Factors' verbatim
    *before* the real section, the parser must pick the real section
    (longest match), not the disclaimer match (first match).
    """
    text = (
        "FORWARD-LOOKING STATEMENTS\n"
        "Factors that might cause such differences include, but are not "
        "limited to, those discussed in Part I, Item 1A. Risk Factors.\n\n"
        "Item 1. Business\n"
        "Apple Inc. designs smartphones.\n\n"
        "Item 1A. Risk Factors\n"
        "Macroeconomic Risks\n"
        "We are exposed to inflation and interest rate changes.\n\n"
        "Supply Chain Risks\n"
        "We depend on TSMC for advanced semiconductors.\n\n"
        "Legal and Regulatory Risks\n"
        "We are subject to global privacy regulations.\n"
        * 20  # pad the body so the real section is much longer than the disclaimer
        + "\n\n"
        "Item 1B. Unresolved Staff Comments\n"
        "None."
    )
    sections = SectionParser().parse(text, prefer_substantive_match=True)
    sec_1a = sections.get("section_1a")
    assert sec_1a is not None
    # The real section starts with "Macroeconomic Risks"; the disclaimer
    # would start with "Factors that might cause".
    assert sec_1a.text.lstrip().startswith("Macroeconomic Risks"), (
        f"Expected real Item 1A body, got disclaimer-like text: "
        f"{sec_1a.text[:120]!r}"
    )
    assert len(sec_1a.text) >= 500, (
        "Substantive match should produce a chunk of >=500 chars"
    )


def test_parser_strips_forward_looking_disclaimer() -> None:
    """The FLS heading paragraph is filtered out of the section body."""
    text = (
        "FORWARD-LOOKING STATEMENTS\n"
        "Factors that might cause such differences include, but are not "
        "limited to, those discussed in Part I, Item 1A. Risk Factors.\n\n"
        "Item 1A. Risk Factors\n"
        + ("The Company is exposed to macroeconomic risks. " * 30)
        + "\n\n"
        "Item 1B. Unresolved Staff Comments\n"
        "None."
    )
    sections = SectionParser().parse(text, prefer_substantive_match=True)
    sec_1a = sections.get("section_1a")
    assert sec_1a is not None
    assert "FORWARD-LOOKING STATEMENTS" not in sec_1a.text
    assert "Macroeconomic" in sec_1a.text


def test_parser_first_match_mode_still_works() -> None:
    """Backward-compat: prefer_substantive_match=False picks the first
    match (used by tests and the FilingFetcher legacy fallback)."""
    text = (
        "Item 1A. Risk Factors\nDisclaimer paragraph.\n\n"
        "Item 1A. Risk Factors\n"
        + ("Real risk body. " * 30)
    )
    sections = SectionParser().parse(text, prefer_substantive_match=False)
    sec_1a = sections.get("section_1a")
    assert sec_1a is not None
    assert "Disclaimer" in sec_1a.text


# ---------------------------------------------------------------------------
# Real Apple-style 10-K fixture (added 2026-06-25)
# ---------------------------------------------------------------------------


def _load_aapl_fixture() -> dict:
    path = Path(__file__).parents[2] / "fixtures" / "real_10k" / "aapl_2023_item_1a.json"
    return json.loads(path.read_text())


def test_real_aapl_fixture_extracts_real_item_1a() -> None:
    """End-to-end: the curated Apple-style fixture exercises every
    improvement (FLS disclaimer trap, NBSP entity, long Item 1A body)
    and the parser picks the real section, not the disclaimer."""
    fixture = _load_aapl_fixture()
    sections = SectionParser().parse(fixture["html"], prefer_substantive_match=True)
    sec_1a = sections.get("section_1a")
    assert sec_1a is not None
    assert sec_1a.char_end - sec_1a.char_start >= fixture["expected_section_1a_min_chars"]
    # The real Item 1A body opens with the boilerplate introduction.
    assert sec_1a.text.lstrip().startswith("The Company's business")
    # All expected subtopics must be present.
    for subtopic in fixture["expected_section_1a_subtopics"]:
        assert subtopic in sec_1a.text, f"missing subtopic: {subtopic}"
    # Item 1B (Unresolved Staff Comments) is also picked because it
    # matches the Item-1B regex — verify it is BOUNDED so it does not
    # bleed into Item 1A.
    if "section_1b" in sections:
        assert sections["section_1b"].char_start >= sec_1a.char_end


def test_real_aapl_fixture_handles_nbsp_in_html() -> None:
    """The fixture uses ``Item&#160;1B.`` and ``Item&#160;1A.`` (NBSP
    entities) — both must resolve correctly via html.unescape +
    NBSP normalisation."""
    fixture = _load_aapl_fixture()
    sections = SectionParser().parse(fixture["html"], prefer_substantive_match=True)
    # Item 1 and Item 1A both have NBSP entities in the source.
    assert "section_1" in sections
    assert "section_1a" in sections
    assert "section_2" in sections