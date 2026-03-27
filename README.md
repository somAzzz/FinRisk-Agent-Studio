# FinText-LLM

Quantamental NLP 系统，利用本地 LLM 分析 SEC EDGAR Filing 与财报电话会，提取结构性金融信号。

将非结构化 SEC 文档转化为可投资的量化信号。

## Features

| Module | Description | Use Case |
|--------|-------------|----------|
| **Macro Risk Alert** | 从 Item 1A 提取宏观风险，1-5 级严重度 | 风险预警 |
| **Management Sentiment Deviation** | 对比 MD&A（书面）与财报电话会 Q&A（口头）情感差异 | 管理层信心分析 |
| **Policy & Transition Risk** | 识别 IRA、碳监管等政策影响 | 政策风险评估 |
| **Second-Order Supply Chain** | 通过知识图谱发现"铲子"机会 | 供应链投资 |
| **Browser Exploration** | LLM 驱动浏览器，实时抓取金融数据 | 动态市场研究 |

## Quick Start

```bash
# Install dependencies
uv sync

# Start LLM service (SGLang with Qwen3.5-35B-A3B)
docker compose up -d

# Download EDGAR data (optional, for local corpus)
python -m src.utils.download_edgar_2020
```

## Core Features

### Browser Exploration

LLM 驱动的 web 探索引擎，用于实时金融数据、市场新闻和研究。

**Architecture**:
```
MarketExplorer (LLM Agent)
├── SGLangClient (LLM with Pydantic Structured Output)
│   └── BrowserAction, PageSummary models
├── BrowserWrapper (agent-browser CLI wrapper)
└── Consent page auto-handling
```

**Setup**:
```bash
# Install agent-browser (Rust headless browser)
cargo install agent-browser
agent-browser install  # Install Chrome
```

**Usage**:
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
        checkpoint_callback=lambda state: len(state.findings) < 5
    )

    for finding in result.findings:
        print(f"[{finding.source_type}] {finding.summary}")

asyncio.run(main())
```

**SGLang Upgrade Path**: 当前使用 OpenAI 兼容 API。sglang 0.6+ 可用时，通过 FSM 约束解码获得更好性能。参见 `docs/sglang_native_reference.py`。

### Web Tools

多工具 Agent 系统，支持智能路由：

- **ddgs** (DuckDuckGo) — 简单查询：fact-check、股票代码、官方网站
- **tavily** — 深度搜索：分析报告、多源新闻、趋势研究（RAG 优化，500 chars 摘要）
- **web_fetch** — URL 内容提取
- **searxng** — ddgs 失败时的透明容错（LLM 不可见）

**Tiered Routing**:
- 关键词规则引擎优先检测，简单/深度查询直接路由，不调 LLM
- 模糊情况 → LLM 路由判断

```python
from src.tools.router import ToolRouter

router = ToolRouter()
# Routes to: ddgs, tavily, web_fetch, browser, or finish
```

### EDGAR Analysis

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

## Architecture

```
Data Sources → Preprocessing (Spark) → LLM Inference (SGLang) → Analysis → API Service (FastAPI + Neo4j)
```

**Hybrid Data Architecture**:
- `edgar-corpus` (HuggingFace) — ~220K SEC filings (1993-2020)，用于回测
- `defeatbeta-api` — 最新财报电话会
- DuckDB — 直接查询 HuggingFace Parquet 文件

## Tech Stack

| Layer | Technology |
|-------|------------|
| **Language** | Python 3.12 |
| **Package Manager** | uv |
| **LLM Engine** | SGLang (Qwen/Qwen3.5-35B-A3B) |
| **Distributed Compute** | PySpark |
| **Graph Database** | Neo4j |
| **API Framework** | FastAPI + Pydantic |
| **Browser Automation** | agent-browser |
| **Container** | Docker + Docker Compose |

## Data Sources

- **HuggingFace**: `eloukas/edgar-corpus` (~220K filings, 1993-2020)
- **HuggingFace**: `Joshua-Xia/yahoo-finance-data` (earnings call transcripts)
- **GitHub**: `lefterisloukas/edgar-crawler` (latest filings)
- **Stock Data**: yfinance

## Project Structure

```
FinText-LLM/
├── src/
│   ├── browser/              # LLM-driven browser exploration
│   │   ├── config.py         # BrowserConfig, ExplorationConfig
│   │   ├── wrapper.py        # BrowserWrapper (agent-browser CLI)
│   │   ├── explorer.py       # MarketExplorer (LLM agent)
│   │   └── sanitize.py       # Sensitive data filter
│   ├── data/
│   │   └── loader.py         # EdgarDataset for EDGAR corpus
│   ├── llm/
│   │   ├── client.py         # EdgarLLMClient for risk extraction
│   │   └── sglang_client.py  # SGLangClient with Pydantic
│   ├── tools/
│   │   ├── router.py         # Tool router (web_search, web_fetch, browser, finish)
│   │   ├── web_search.py      # DuckDuckGo search with time_range
│   │   └── web_fetch.py       # URL content extraction
│   └── utils/
│       └── download_edgar_2020.py
├── scripts/
│   ├── demo_exploration.py    # Browser exploration demo
│   └── demo_web_search.py     # Web search demo
├── docs/
│   └── sglang_native_reference.py  # Future upgrade reference
├── docker-compose.yml
├── pyproject.toml
└── README.md
```

## Developer Guide

```bash
# Run tests
pytest

# Lint
ruff check .

# Install dependencies
uv sync
```

## License

This project includes data from Yahoo Finance, licensed under ODC-BY.
