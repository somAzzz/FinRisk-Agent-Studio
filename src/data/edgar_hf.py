"""Hugging Face streaming loader for the EDGAR 10-K corpus."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import Any

import datasets

from src.data.filing_utils import extract_year, iter_sections
from src.schemas.filings import FilingRecord

DEFAULT_DATASET_NAME = "eloukas/edgar-corpus"
DEFAULT_CONFIG_NAME = "year_2020"
DEFAULT_SPLIT = "train"
DEFAULT_REQUIRED_SECTIONS: tuple[str, ...] = ("section_1A",)
DEFAULT_MIN_SECTION_LENGTH = 100


class EdgarCorpusLoader:
    """Streaming-first loader for the Hugging Face ``eloukas/edgar-corpus`` dataset.

    Maps raw rows into :class:`FilingRecord` instances while filtering out rows
    that are missing required sections or whose sections are too short.
    """

    def __init__(
        self,
        dataset_name: str = DEFAULT_DATASET_NAME,
        config_name: str = DEFAULT_CONFIG_NAME,
        split: str = DEFAULT_SPLIT,
        streaming: bool = True,
    ) -> None:
        """Store loader configuration.

        Args:
            dataset_name: Hugging Face dataset identifier.
            config_name: Dataset config (typically a year like ``year_2020``).
            split: Dataset split to load.
            streaming: Whether to stream the dataset rather than downloading it.
        """
        self.dataset_name = dataset_name
        self.config_name = config_name
        self.split = split
        self.streaming = streaming

    def _load(self) -> Any:
        """Invoke :func:`datasets.load_dataset` with the configured arguments."""
        return datasets.load_dataset(
            self.dataset_name,
            self.config_name,
            split=self.split,
            streaming=self.streaming,
        )

    def iter_filings(
        self,
        min_section_length: int = DEFAULT_MIN_SECTION_LENGTH,
        required_sections: Sequence[str] = DEFAULT_REQUIRED_SECTIONS,
        limit: int | None = None,
    ) -> Iterator[FilingRecord]:
        """Iterate over filings as :class:`FilingRecord` instances.

        Args:
            min_section_length: Minimum character length for any required section.
            required_sections: Section names that must exist and meet the length bar.
            limit: Optional cap on the number of records yielded.

        Yields:
            Validated :class:`FilingRecord` objects.
        """
        dataset = self._load()
        yielded = 0

        for row_index, row in enumerate(dataset):
            sections: dict[str, str] = dict(iter_sections(row))
            metadata: dict[str, Any] = {}

            filename = row.get("filename") if isinstance(row, dict) else None
            if filename is not None:
                metadata["filename"] = filename

            for key, value in row.items():
                if not isinstance(key, str):
                    continue
                if key.startswith("section_"):
                    continue
                if key in {"cik", "year", "filename"}:
                    continue
                metadata[key] = value

            required_ok = all(
                isinstance(sections.get(name), str)
                and len(sections[name]) >= min_section_length
                for name in required_sections
            )
            if not required_ok:
                continue

            cik_value = row.get("cik") if isinstance(row, dict) else None
            cik = str(cik_value) if cik_value is not None else ""

            year_value = row.get("year") if isinstance(row, dict) else None
            year = extract_year(year_value)

            source_id = (
                f"hf:{self.dataset_name}:{self.config_name}:{self.split}:{row_index}"
            )

            yield FilingRecord(
                source="huggingface",
                cik=cik,
                year=year,
                sections=sections,
                metadata={**metadata, "source_id": source_id},
            )

            yielded += 1
            if limit is not None and yielded >= limit:
                return

    def count(
        self,
        min_section_length: int = DEFAULT_MIN_SECTION_LENGTH,
        required_sections: Sequence[str] = DEFAULT_REQUIRED_SECTIONS,
        limit: int | None = None,
    ) -> int:
        """Return the total number of filings emitted by :meth:`iter_filings`."""
        return sum(
            1
            for _ in self.iter_filings(
                min_section_length=min_section_length,
                required_sections=required_sections,
                limit=limit,
            )
        )
