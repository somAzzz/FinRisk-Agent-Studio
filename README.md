# FinText-LLM

SEC EDGAR filing analysis system using local LLM + Spark + Neo4j

## Features

- **Macro Risk Alert** - Extract macro risks from Item 1A (Risk Factors) with severity scores
- **Management Sentiment Deviation** - Compare MD&A vs earnings call Q&A sentiment
- **Policy & Transition Risk** - Identify IRA, carbon regulation impacts
- **Second-Order Supply Chain Discovery** - Find "pick-and-shovel" opportunities via knowledge graph

## Tech Stack

- **Language**: Python 3.12
- **Package Manager**: uv
- **LLM Engine**: sglang (Qwen/Qwen3.5-35B-A3B)
- **Distributed Compute**: PySpark
- **Graph Database**: Neo4j
- **API Framework**: FastAPI + Pydantic
- **Container**: Docker + Docker Compose

## Data Sources

- **HuggingFace**: `eloukas/edgar-corpus` (~220K filings, 1993-2020)
- **HuggingFace**: `Joshua-Xia/yahoo-finance-data` (earnings call transcripts)
- **GitHub**: lefterisloukas/edgar-crawler (latest filings)
- **Stock Data**: yfinance

## Quick Start

```bash
# Install dependencies
uv sync

# Start sglang server
docker compose up -d

# Download EDGAR data
python -m src.utils.download_edgar_2020
```

## Usage

```python
# Load EDGAR filings
from src.data.loader import EdgarDataset

ds = EdgarDataset()
for filing in ds.get_filings_with_content("train"):
    print(filing["cik"], filing["year"])

# Extract risks using LLM
from src.llm.client import EdgarLLMClient

client = EdgarLLMClient()
result = client.extract_risks(section_1a, company_name="Apple")
```

## Project Structure

```
FinText-LLM/
├── src/
│   ├── data/
│   │   └── loader.py       # EDGAR filing loader
│   ├── llm/
│   │   └── client.py       # sglang client for risk extraction
│   └── utils/
│       └── download_edgar_2020.py
├── docker-compose.yml
├── pyproject.toml
└── README.md
```

## License

This project includes data from Yahoo Finance, licensed under ODC-BY.
