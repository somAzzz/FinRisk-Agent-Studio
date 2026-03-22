"""Download eloukas/edgar-corpus dataset for year 2020."""

import json
import os
import shutil
from pathlib import Path

from huggingface_hub import hf_hub_download

DEFAULT_DATA_DIR = os.environ.get("EDGAR_DATA_DIR", "/home/bo/projects/data")
REPO_ID = "eloukas/edgar-corpus"
YEAR = "2020"
SPLITS = ("train", "validate", "test")


def get_data_dir() -> Path:
    """Get the data directory path from environment or default."""
    return Path(DEFAULT_DATA_DIR) / "edgar_2020"


def download_split(split: str, data_dir: Path) -> None:
    """Download a single split of the dataset.

    Args:
        split: Split name (train, validate, test)
        data_dir: Directory to save the file
    """
    print(f"Downloading {split}.jsonl...")
    filepath = hf_hub_download(
        repo_id=REPO_ID,
        filename=f"{YEAR}/{split}.jsonl",
        repo_type="dataset",
    )
    # Copy to our data directory (file is a symlink, so copy instead)
    dest_path = data_dir / f"{split}.jsonl"
    shutil.copy(filepath, dest_path)
    print(f"Saved to {dest_path}")


def count_records(data_dir: Path) -> dict[str, int]:
    """Count records in each split.

    Args:
        data_dir: Directory containing the dataset files

    Returns:
        Dictionary mapping split names to record counts
    """
    counts = {}
    for split in SPLITS:
        path = data_dir / f"{split}.jsonl"
        with open(path) as f:
            counts[split] = sum(1 for _ in f)
    return counts


def print_summary(counts: dict[str, int]) -> None:
    """Print dataset summary.

    Args:
        counts: Dictionary of split counts
    """
    print("\n--- Dataset Summary ---")
    for split, count in counts.items():
        print(f"{split}: {count} records")


def print_sample(data_dir: Path) -> None:
    """Print a sample record.

    Args:
        data_dir: Directory containing the dataset files
    """
    print("\n--- Sample Record ---")
    with open(data_dir / "train.jsonl") as f:
        sample = json.loads(f.readline())
        print(f"CIK: {sample['cik']}")
        print(f"Year: {sample['year']}")
        print(f"Filename: {sample['filename']}")
        print(f"Section 1A length: {len(sample.get('section_1A', '') or '')}")
        print(f"Section 1 (Business) length: {len(sample.get('section_1', '') or '')}")
        print(f"Section 7 (MD&A) length: {len(sample.get('section_7', '') or '')}")


def main() -> None:
    """Download the EDGAR corpus dataset for 2020."""
    data_dir = get_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)

    # Download each split
    for split in SPLITS:
        download_split(split, data_dir)

    # Count records
    counts = count_records(data_dir)
    print_summary(counts)

    # Show sample
    print_sample(data_dir)


if __name__ == "__main__":
    main()
