"""Data loader for EDGAR corpus dataset."""

import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import TypedDict

DEFAULT_DATA_DIR = os.environ.get(
    "EDGAR_DATA_DIR",
    "/home/bo/projects/python/fintext_llm/data/edgar_2020",
)
MIN_SECTION_LENGTH = 100


class Filing(TypedDict):
    """Type for EDGAR filing data."""

    cik: str
    year: int
    section_1A: str
    section_1: str
    section_7: str
    filename: str


class EdgarDataset:
    """Loader for EDGAR 10-K filings corpus."""

    VALID_SPLITS = ("train", "validate", "test")

    def __init__(self, data_dir: str | None = None):
        self.data_dir = Path(data_dir) if data_dir else Path(DEFAULT_DATA_DIR)

    def iter_filings(self, split: str = "train") -> Iterator[Filing]:
        """Iterate over filings in a split.

        Args:
            split: One of 'train', 'validate', 'test'

        Yields:
            Filing data dictionary (cik, year, section_1, section_1A, etc.)

        Raises:
            ValueError: If split is not valid
        """
        if split not in self.VALID_SPLITS:
            raise ValueError(
                f"Invalid split: {split}. Must be one of {self.VALID_SPLITS}"
            )

        filepath = self.data_dir / f"{split}.jsonl"
        with open(filepath) as f:
            for line in f:
                yield json.loads(line)

    def get_filings_with_content(
        self,
        split: str = "train",
        min_length: int = MIN_SECTION_LENGTH,
    ) -> Iterator[Filing]:
        """Iterate over filings that have meaningful content in key sections.

        Filters out filings where section_1A (Risk Factors) is empty or too short.

        Args:
            split: One of 'train', 'validate', 'test'
            min_length: Minimum required length for section_1A

        Yields:
            Filing data dictionaries with meaningful content
        """
        for filing in self.iter_filings(split):
            if len(filing.get("section_1A", "") or "") > min_length:
                yield filing


if __name__ == "__main__":
    ds = EdgarDataset()
    print("=== EdgarDataset Demo ===")

    # Count filings
    total = sum(1 for _ in ds.iter_filings("train"))
    print(f"Total train filings: {total}")

    # Count filings with meaningful content
    with_content = sum(1 for _ in ds.get_filings_with_content("train"))
    print(f"Filings with section_1A > {MIN_SECTION_LENGTH} chars: {with_content}")

    # Sample
    sample = next(ds.get_filings_with_content("train"))
    print(f"\nSample CIK: {sample['cik']}")
    print(f"Year: {sample['year']}")
    print("Section 1A (Risk Factors) first 200 chars:")
    print(sample.get("section_1A", "")[:2000])
