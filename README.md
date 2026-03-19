# FinText-LLM

SEC EDGAR filing analysis system using local LLM + Spark + Neo4j

## Features

- **Macro Risk Alert** - Extract macro risks from Item 1A (Risk Factors) with severity scores
- **Management Sentiment Deviation** - Compare MD&A vs earnings call Q&A sentiment
- **Policy & Transition Risk** - Identify IRA, carbon regulation impacts
- **Second-Order Supply Chain Discovery** - Find "pick-and-shovel" opportunities via knowledge graph
- **Browser Exploration** - LLM-driven web exploration for real-time financial data (agent-browser + SGLang)

## Tech Stack

- **Language**: Python 3.12
- **Package Manager**: uv
- **LLM Engine**: sglang (Qwen/Qwen3.5-35B-A3B)
- **Distributed Compute**: PySpark
- **Graph Database**: Neo4j
- **API Framework**: FastAPI + Pydantic
- **Container**: Docker + Docker Compose
- **Browser Automation**: agent-browser (Rust headless browser CLI)

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

## Browser Exploration

LLM-driven web exploration for real-time financial data, news, and market research.

### Setup

```bash
# Install agent-browser (Rust headless browser)
cargo install agent-browser
agent-browser install  # Install Chrome
```

### Usage

```python
import asyncio
from src.browser import BrowserWrapper, MarketExplorer
from src.llm.sglang_client import SGLangClient

async def main():
    explorer = MarketExplorer(
        llm_client=SGLangClient(),
        wrapper=BrowserWrapper()
    )

    result = await explorer.explore(
        goal="Explore Apple's latest earnings news and analyst opinions",
        checkpoint_callback=lambda state: len(state.findings) < 5  # Auto-stop at 5
    )

    for finding in result.findings:
        print(f"[{finding.source_type}] {finding.summary}")

asyncio.run(main())
```

### Architecture

```
MarketExplorer (LLM Agent)
    ├── SGLangClient (LLM with Pydantic Structured Output)
    │   └── BrowserAction, PageSummary models
    ├── BrowserWrapper (agent-browser CLI wrapper)
    └── Consent page auto-handling
```

### SGLang Upgrade Path

Current implementation uses OpenAI-compatible API with `client.beta.chat.completions.parse()`.

When sglang 0.6+ is available, native frontend syntax will provide better performance via FSM-based constrained decoding:

```python
# See docs/sglang_native_reference.py for native implementation
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
│   ├── browser/              # Browser exploration module
│   │   ├── config.py         # BrowserConfig, ExplorationConfig
│   │   ├── wrapper.py        # BrowserWrapper (agent-browser CLI)
│   │   ├── explorer.py       # MarketExplorer (LLM agent)
│   │   └── sanitize.py       # Sensitive data filter
│   ├── data/
│   │   └── loader.py         # EDGAR filing loader
│   ├── llm/
│   │   ├── client.py         # EdgarLLMClient for risk extraction
│   │   └── sglang_client.py  # SGLangClient with Pydantic
│   └── utils/
│       └── download_edgar_2020.py
├── scripts/
│   └── demo_exploration.py    # Browser exploration demo
├── docs/
│   └── sglang_native_reference.py  # Future upgrade reference
├── docker-compose.yml
├── pyproject.toml
└── README.md
```

## License

This project includes data from Yahoo Finance, licensed under ODC-BY.
