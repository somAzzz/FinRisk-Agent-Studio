# EDGAR-CORPUS Dataset

## Overview

| Property | Value |
|----------|-------|
| **Dataset Name** | eloukas/edgar-corpus |
| **Creator** | Lefteris Loukas |
| **License** | Apache-2.0 |
| **Language** | English |
| **Task Category** | Raw dataset/corpus |
| **Size** | 100K < n < 1M |
| **ArXiv Paper** | arxiv:2109.14394 |

## Local Data Structure

This project uses the year 2020 data downloaded to `data/edgar_2020/`:

```
data/edgar_2020/
├── train.jsonl    # 5,480 filings
├── validate.jsonl # 686 filings
└── test.jsonl    # 685 filings
```

### JSONL Record Format

Each line is a JSON object with:

| Field | Type | Description |
|-------|------|-------------|
| `filename` | string | EDGAR filename (e.g., "718413_2020.htm") |
| `cik` | string | EDGAR company identifier |
| `year` | string | Report year ("2020") |
| `section_1` | string | Item 1 - Business (full text) |
| `section_1A` | string | Item 1A - Risk Factors (full text) |
| `section_1B` | string | Item 1B - Unresolved Staff Comments |
| `section_2` - `section_15` | string | Other 10-K sections |

### Sample Record

```json
{
  "filename": "718413_2020.htm",
  "cik": "718413",
  "year": "2020",
  "section_1": "Item 1. Business\nCompany Background...",
  "section_1A": "Item 1A. Risk Factors\nBefore deciding to invest...",
  "section_7": "Item 7. MD&A..."
}
```

### Data Loading

```python
from src.data import EdgarDataset

ds = EdgarDataset()

# Iterate all filings
for filing in ds.iter_filings("train"):
    print(filing["cik"], filing["year"])

# Filter for meaningful content
for filing in ds.get_filings_with_content("train"):
    # section_1A (Risk Factors) > 100 chars
    print(filing["section_1A"][:200])
```

## Description

The EDGAR-CORPUS dataset contains **annual reports (10-K filings)** of all publicly traded firms from **1993-2020** from SEC EDGAR filings. Table data is stripped but all text is retained.

Based on the paper *"EDGAR-CORPUS: Billions of Tokens Make The World Go Round"* published at **ECONLP 2021** (Third Workshop on Economics and Natural Language Processing).

## Dataset Structure

### Data Fields

| Field | Description |
|-------|-------------|
| `filename` | Name of file on EDGAR from which the report was extracted |
| `cik` | EDGAR identifier for a firm |
| `year` | Year of report |
| `section_1` - `section_15` | Corresponding sections of the Annual Report (including subsections like `section_1A`, `section_1B`, `section_7A`, `section_9A`, `section_9B`) |

### Key Sections for This Project

| Section | Item | Description |
|---------|------|-------------|
| `section_1` | Item 1 | Business Description |
| `section_1A` | Item 1A | Risk Factors |
| `section_7` | Item 7 | Management's Discussion and Analysis (MD&A) |
| `section_7A` | Item 7A | Market Risk Disclosure |

## Configurations

```python
import datasets

# Load the entire dataset
raw_dataset = datasets.load_dataset("eloukas/edgar-corpus", "full")

# Load a specific year
year_2020_training = datasets.load_dataset("eloukas/edgar-corpus", "year_2020", split="train")
year_2020_test = datasets.load_dataset("eloukas/edgar-corpus", "year_2020", split="test")
```

Available configs: `full`, `year_1993`, `year_1994`, ..., `year_2020`

## Data Splits

| Config | Train | Validation | Test |
|--------|-------|------------|------|
| **full** | 176,289 | 22,050 | 22,036 |
| year_1993 | 1,060 | 133 | 133 |
| year_1994 | 2,083 | 261 | 260 |
| year_1995 | 2,310 | 289 | 289 |
| year_1996 | 2,573 | 322 | 321 |
| year_1997 | 2,816 | 352 | 352 |
| year_1998 | 3,071 | 384 | 383 |
| year_1999 | 3,378 | 422 | 422 |
| year_2000 | 3,741 | 468 | 467 |
| year_2001 | 4,004 | 500 | 500 |
| year_2002 | 4,161 | 520 | 520 |
| year_2003 | 4,305 | 538 | 538 |
| year_2004 | 4,435 | 554 | 554 |
| year_2005 | 4,574 | 572 | 571 |
| year_2006 | 4,703 | 588 | 587 |
| year_2007 | 4,836 | 604 | 604 |
| year_2008 | 4,970 | 621 | 621 |
| year_2009 | 5,067 | 633 | 633 |
| year_2010 | 5,152 | 644 | 644 |
| year_2011 | 5,218 | 652 | 652 |
| year_2012 | 5,265 | 658 | 658 |
| year_2013 | 5,280 | 660 | 660 |
| year_2014 | 5,305 | 663 | 663 |
| year_2015 | 5,352 | 669 | 669 |
| year_2016 | 5,365 | 671 | 670 |
| year_2017 | 5,406 | 676 | 675 |
| year_2018 | 5,440 | 680 | 680 |
| year_2019 | 5,475 | 684 | 684 |
| year_2020 | 5,480 | 686 | 685 |

## Usage Notes

- This is a raw corpus dataset; train/val/test splits have no special semantic meaning
- To load specific year(s) of specific companies, use the open-source **EDGAR-CRAWLER**: https://github.com/nlpaueb/edgar-crawler
- The dataset requires arbitrary Python code execution, so the Dataset Viewer is disabled on HuggingFace

## Citation

```bibtex
@inproceedings{loukas-etal-2021-edgar,
    title = "{EDGAR}-{CORPUS}: Billions of Tokens Make The World Go Round",
    author = "Loukas, Lefteris and Fergadiotis, Manos and Androutsopoulos, Ion and Malakasiotis, Prodromos",
    booktitle = "Proceedings of the Third Workshop on Economics and Natural Language Processing",
    month = nov,
    year = "2021",
    address = "Punta Cana, Dominican Republic",
    publisher = "Association for Computational Linguistics",
    url = "https://aclanthology.org/2021.econlp-1.2",
    pages = "13--18",
}
```

## Statistics Summary

| Metric | Value |
|--------|-------|
| Time Range | 1993 - 2020 |
| Total Records | ~220,000 (full) |
| Annual Growth | ~180 records/year |
| Sections per Record | 15 |

## Relevant Sections for Analysis

### Module 1: Macro Risk Alert
- **Source**: `section_1A` (Item 1A - Risk Factors)
- **Content**: Macroeconomic risks, industry risks, regulatory risks

### Module 2: Management Sentiment Deviation
- **Source**: `section_7` (Item 7 - MD&A)
- **Content**: Management's discussion of financial results, risks, and future outlook

### Module 3: Policy & Transition Risk
- **Source**: `section_1`, `section_1A`, `section_7`
- **Content**: Business description, risk factors, policy impacts

### Module 4: Supply Chain Discovery
- **Source**: `section_1` (Item 1 - Business)
- **Content**: Business operations, suppliers, capital expenditures

## Data Source

- SEC EDGAR (Electronic Data Gathering, Analysis, and Retrieval system)
- All publicly traded firms filing 10-K annual reports
- EDGAR data is publicly available; dataset licensed under Apache-2.0

---

# EDGAR-CRAWLER (GitHub Tool)

## Overview

| Property | Value |
|----------|-------|
| **Repository** | github.com/lefterisloukas/edgar-crawler |
| **License** | GPL-3.0 |
| **Stars** | 480 |
| **Forks** | 124 |
| **Presented** | WWW 2025, Sydney |

## Description

EDGAR-CRAWLER is an open-source toolkit that downloads SEC EDGAR financial reports and extracts textual data from specific item sections into structured JSON files.

## Supported Filings

| Type | Description |
|------|-------------|
| 10-K | Annual Report |
| 10-Q | Quarterly Report |
| 8-K | Important Current Report |

## Installation

```bash
# Clone the repository
git clone https://github.com/nlpaueb/edgar-crawler.git

# Create virtual environment
conda create -n edgar-crawler-venv python=3.8
conda activate edgar-crawler-venv

# Install dependencies
pip install -r requirements.txt
```

## Configuration

Edit `config.json` to configure the crawler.

### download_filings.py Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `start_year` | Year range start | 2023 |
| `end_year` | Year range end | 2023 |
| `quarters` | List of quarters | [1, 2, 3, 4] |
| `filing_types` | Types to download | ['10-K', '8-K', '10-Q'] |
| `cik_tickers` | CIKs or Tickers list/file | All US companies |
| `user_agent` | User-agent for SEC EDGAR | Required |
| `raw_filings_folder` | Downloaded filings storage | 'RAW_FILINGS' |
| `indices_folder` | EDGAR TSV files storage | 'INDICES' |
| `skip_present_indices` | Skip already downloaded indices | True |

### extract_items.py Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `raw_filings_folder` | Downloaded documents location | 'RAW_FILINGS' |
| `extracted_filings_folder` | Extracted output location | 'EXTRACTED_FILINGS' |
| `filing_types` | Types to extract | Required |
| `items_to_extract` | Specific items to extract | All items |
| `remove_tables` | Remove numerical tables | False |
| `skip_extracted_filings` | Skip already extracted | True |

## Commands

```bash
# Download raw financial reports
python download_filings.py

# Extract and clean specific item sections
python extract_items.py
```

## Output Format

The tool produces JSON files with structured data:

```json
{
  "cik": "320193",
  "company": "Apple Inc.",
": "10-K",
  "filing  "filing_type_date": "2022-10-28",
  "period_of_report": "2022-09-24",
  "item_1": "Item 1. Business\nCompany Background...",
  "item_1A": "Item 1A. Risk Factors...",
  "item_7": "Item 7. Management's Discussion..."
}
```

## Use Case for This Project

- **HuggingFace (edgar-corpus)**: Fast startup, historical data (1993-2020), ~220K filings
- **edgar-crawler**: Latest filings (2021+), custom company filtering, fresh data

## Citation

When using EDGAR-CRAWLER, please cite:

1. **EDGAR-CRAWLER** @ WWW 2025 (https://dl.acm.org/doi/10.1145/3701716.3715289)
2. **EDGAR-CORPUS** @ ECONLP Workshop, EMNLP 2021 (https://aclanthology.org/2021.econlp-1.2/)
