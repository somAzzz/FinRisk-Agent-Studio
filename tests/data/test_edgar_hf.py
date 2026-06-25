"""Unit tests for :class:`src.data.edgar_hf.EdgarCorpusLoader`.

These tests mock :func:`datasets.load_dataset` and never touch the network.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from src.data import edgar_hf
from src.data.edgar_hf import EdgarCorpusLoader


def _fake_dataset(rows: list[dict]) -> Iterator[dict]:
    return iter(rows)


def _patch_load_dataset(
    monkeypatch: pytest.MonkeyPatch,
    rows: list[dict],
    captured: dict[str, Any] | None = None,
) -> None:
    """Patch ``datasets.load_dataset`` to return a fake iterable of rows."""

    def _fake_load(dataset_name: str, config_name: str, split: str, streaming: bool):
        if captured is not None:
            captured.update(
                {
                    "dataset_name": dataset_name,
                    "config_name": config_name,
                    "split": split,
                    "streaming": streaming,
                }
            )
        return _fake_dataset(rows)

    monkeypatch.setattr(edgar_hf.datasets, "load_dataset", _fake_load)


def test_iter_filings_passes_streaming_true(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}
    _patch_load_dataset(
        monkeypatch,
        [
            {
                "cik": "1",
                "year": 2020,
                "filename": "a.txt",
                "section_1A": "x" * 200,
            }
        ],
        captured=captured,
    )

    loader = EdgarCorpusLoader()
    list(loader.iter_filings(limit=1))

    assert captured["streaming"] is True
    assert captured["dataset_name"] == "eloukas/edgar-corpus"
    assert captured["config_name"] == "year_2020"
    assert captured["split"] == "train"


def test_iter_filings_maps_hf_record_to_filing_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_load_dataset(
        monkeypatch,
        [
            {
                "cik": 12345,
                "year": 2020,
                "filename": "sample.txt",
                "section_1": "Business",
                "section_1A": "Risk Factors " * 20,
                "section_7": "MD&A " * 20,
            }
        ],
    )

    loader = EdgarCorpusLoader()
    [record] = list(loader.iter_filings(limit=1))

    assert record.source == "huggingface"
    assert record.cik == "12345"
    assert record.year == 2020
    assert record.sections["section_1"] == "Business"
    assert record.sections["section_1A"].startswith("Risk Factors")
    assert record.sections["section_7"].startswith("MD&A")
    assert record.metadata["filename"] == "sample.txt"
    assert record.metadata["source_id"] == "hf:eloukas/edgar-corpus:year_2020:train:0"


def test_iter_filings_required_section_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [
        {
            "cik": "1",
            "year": 2020,
            "filename": "ok.txt",
            "section_1A": "x" * 200,
        },
        {
            "cik": "2",
            "year": 2020,
            "filename": "short.txt",
            "section_1A": "too short",
        },
        {
            "cik": "3",
            "year": 2020,
            "filename": "missing.txt",
        },
    ]
    _patch_load_dataset(monkeypatch, rows)

    loader = EdgarCorpusLoader()
    records = list(loader.iter_filings(min_section_length=100, limit=10))

    assert len(records) == 1
    assert records[0].cik == "1"
    assert records[0].metadata["filename"] == "ok.txt"


def test_iter_filings_limit_argument(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [
        {
            "cik": str(i),
            "year": 2020,
            "filename": f"f{i}.txt",
            "section_1A": "x" * 200,
        }
        for i in range(5)
    ]
    _patch_load_dataset(monkeypatch, rows)

    loader = EdgarCorpusLoader()
    records = list(loader.iter_filings(limit=2))

    assert len(records) == 2
    assert [r.cik for r in records] == ["0", "1"]


def test_iter_filings_year_from_string(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_load_dataset(
        monkeypatch,
        [
            {
                "cik": "1",
                "year": "2019",
                "filename": "a.txt",
                "section_1A": "x" * 200,
            }
        ],
    )

    loader = EdgarCorpusLoader()
    [record] = list(loader.iter_filings(limit=1))

    assert record.year == 2019
    assert isinstance(record.year, int)


def test_iter_filings_year_from_int(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_load_dataset(
        monkeypatch,
        [
            {
                "cik": "1",
                "year": 2018,
                "filename": "a.txt",
                "section_1A": "x" * 200,
            }
        ],
    )

    loader = EdgarCorpusLoader()
    [record] = list(loader.iter_filings(limit=1))

    assert record.year == 2018


def test_iter_filings_year_unparseable(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_load_dataset(
        monkeypatch,
        [
            {
                "cik": "1",
                "year": "not-a-year",
                "filename": "a.txt",
                "section_1A": "x" * 200,
            }
        ],
    )

    loader = EdgarCorpusLoader()
    [record] = list(loader.iter_filings(limit=1))

    assert record.year is None


def test_iter_filings_source_id_format(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [
        {
            "cik": "1",
            "year": 2020,
            "filename": "a.txt",
            "section_1A": "x" * 200,
        },
        {
            "cik": "2",
            "year": 2020,
            "filename": "b.txt",
            "section_1A": "x" * 200,
        },
    ]
    _patch_load_dataset(monkeypatch, rows)

    loader = EdgarCorpusLoader(config_name="year_2021", split="validate")
    records = list(loader.iter_filings(limit=2))

    assert records[0].metadata["source_id"] == "hf:eloukas/edgar-corpus:year_2021:validate:0"
    assert records[1].metadata["source_id"] == "hf:eloukas/edgar-corpus:year_2021:validate:1"


def test_iter_filings_collects_extra_sections(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_load_dataset(
        monkeypatch,
        [
            {
                "cik": "1",
                "year": 2020,
                "filename": "a.txt",
                "section_1": "Business",
                "section_1A": "Risk " * 50,
                "section_7": "MD&A",
                "section_9A": "Controls",
            }
        ],
    )

    loader = EdgarCorpusLoader()
    [record] = list(loader.iter_filings(limit=1))

    assert set(record.sections) == {"section_1", "section_1A", "section_7", "section_9A"}
    assert record.sections["section_9A"] == "Controls"


def test_iter_filings_stores_non_section_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_load_dataset(
        monkeypatch,
        [
            {
                "cik": "1",
                "year": 2020,
                "filename": "a.txt",
                "section_1A": "x" * 200,
                "extra_field": "extra-value",
            }
        ],
    )

    loader = EdgarCorpusLoader()
    [record] = list(loader.iter_filings(limit=1))

    assert record.metadata["extra_field"] == "extra-value"
    assert record.metadata["filename"] == "a.txt"


def test_count_helper(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [
        {
            "cik": str(i),
            "year": 2020,
            "filename": f"f{i}.txt",
            "section_1A": "x" * 200,
        }
        for i in range(3)
    ]
    _patch_load_dataset(monkeypatch, rows)

    loader = EdgarCorpusLoader()
    assert loader.count() == 3
    assert loader.count(limit=2) == 2
