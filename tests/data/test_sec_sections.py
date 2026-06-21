"""Tests for ``src.data.sec_sections.SectionParser``."""

from __future__ import annotations

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
    # First section should start with Item 1.
    assert sections["section_1"].text.startswith("Item 1")
    # Section 1A should contain the risk text.
    assert "supply chain disruptions" in sections["section_1a"].text


def test_parser_preserves_full_text_fallback() -> None:
    parser = SectionParser()
    sections = parser.parse(_10k_text())
    assert "full_text" in sections
    assert sections["full_text"].text == _10k_text().strip()


def test_parser_handles_em_dash_separator() -> None:
    text = (
        "Cover\n"
        "Item 1 — Business\n"
        "We sell widgets.\n"
        "Item 1A — Risk Factors\n"
        "We face supply risks.\n"
    )
    parser = SectionParser()
    sections = parser.parse(text)
    assert "section_1" in sections
    assert "widgets" in sections["section_1"].text
    assert "supply risks" in sections["section_1a"].text


def test_parser_handles_roman_numerals() -> None:
    text = (
        "Item I. Business\n"
        "We sell widgets.\n"
        "Item II. Properties\n"
        "We lease 5 buildings.\n"
        "Item III. Legal Proceedings\n"
        "None material.\n"
    )
    parser = SectionParser()
    sections = parser.parse(text)
    assert "section_1" in sections
    assert "section_2" in sections


def test_parser_records_char_offsets() -> None:
    parser = SectionParser()
    sections = parser.parse(_10k_text())
    sec1 = sections["section_1"]
    assert sec1.char_start >= 0
    assert sec1.char_end > sec1.char_start


def test_parser_handles_empty_html() -> None:
    parser = SectionParser()
    sections = parser.parse("")
    assert "full_text" in sections
    assert sections["full_text"].text == ""


def test_parser_handles_html_input() -> None:
    html = (
        "<html><body>"
        "<h1>Item 1. Business</h1>"
        "<p>We sell widgets.</p>"
        "<h1>Item 1A. Risk Factors</h1>"
        "<p>Supply chain risks.</p>"
        "</body></html>"
    )
    parser = SectionParser()
    sections = parser.parse(html)
    assert "section_1" in sections
    assert "section_1a" in sections
    assert "widgets" in sections["section_1"].text


def test_parser_pattern_dict_has_canonical_keys() -> None:
    for key in (
        "section_1",
        "section_1a",
        "section_2",
        "section_7",
        "section_7a",
    ):
        assert key in SECTION_PATTERNS
