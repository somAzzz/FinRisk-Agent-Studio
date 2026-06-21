"""Unit tests for ``src.data.filing_utils``."""

from __future__ import annotations

import pytest

from src.data.filing_utils import extract_year, iter_sections


def test_iter_sections_yields_only_section_keys() -> None:
    row = {
        "cik": "12345",
        "year": 2020,
        "filename": "file.txt",
        "section_1": "Business content",
        "section_1A": "Risk factors",
        "section_7": "MD&A",
    }

    result = dict(iter_sections(row))

    assert result == {
        "section_1": "Business content",
        "section_1A": "Risk factors",
        "section_7": "MD&A",
    }


def test_iter_sections_handles_non_string_values() -> None:
    row = {"section_1": 123, "section_1A": None}

    result = dict(iter_sections(row))

    assert result == {"section_1": "123", "section_1A": "None"}


def test_iter_sections_ignores_non_string_keys() -> None:
    row = {1: "ignored", "section_1A": "kept"}

    result = dict(iter_sections(row))

    assert result == {"section_1A": "kept"}


def test_extract_year_from_int() -> None:
    assert extract_year(2020) == 2020


def test_extract_year_from_string() -> None:
    assert extract_year("2021") == 2021


def test_extract_year_from_float_integer() -> None:
    assert extract_year(2019.0) == 2019


def test_extract_year_from_none() -> None:
    assert extract_year(None) is None


def test_extract_year_from_invalid_string() -> None:
    assert extract_year("not-a-year") is None


def test_extract_year_from_empty_string() -> None:
    assert extract_year("") is None
    assert extract_year("   ") is None


def test_extract_year_rejects_bool() -> None:
    assert extract_year(True) is None
    assert extract_year(False) is None


def test_extract_year_rejects_non_integer_float() -> None:
    assert extract_year(2020.5) is None


@pytest.mark.parametrize("value,expected", [(2020, 2020), ("2020", 2020), (2020.0, 2020)])
def test_extract_year_parametrized(value: object, expected: int | None) -> None:
    assert extract_year(value) == expected
