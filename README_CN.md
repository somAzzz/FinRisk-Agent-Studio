# FinText-LLM

基于本地 LLM + Spark + Neo4j 的 SEC EDGAR  filings 分析系统

## 功能

- **宏观风险预警** - 从 Item 1A（风险因素）中提取宏观风险并评分
- **管理层情绪偏差** - 对比 MD&A 与财报电话会议 Q&A 的情绪差异
- **政策与转型风险** - 识别 IRA、碳监管影响
- **二级供应链发现** - 通过知识图谱寻找"铲子"机会

## 技术栈

- **语言**: Python 3.12
- **包管理**: uv
- **LLM 引擎**: vLLM (Qwen2.5:7b-instruct)
- **分布式计算**: PySpark
- **图数据库**: Neo4j
- **API 框架**: FastAPI + Pydantic
- **容器**: Docker + Docker Compose

## 数据源

- **HuggingFace**: `eloukas/edgar-corpus` (~220K filings, 1993-2020)
- **HuggingFace**: `Joshua-Xia/yahoo-finance-data` (财报电话会议 transcript)
- **GitHub**: lefterisloukas/edgar-crawler (最新 filings)
- **股票数据**: yfinance

## 快速开始

```bash
# 安装依赖
uv sync

# 启动 vLLM 服务器
docker compose up -d

# 下载 EDGAR 数据
python -m src.utils.download_edgar_2020
```

## 使用方法

```python
# 加载 EDGAR filings
from src.data.loader import EdgarDataset

ds = EdgarDataset()
for filing in ds.get_filings_with_content("train"):
    print(filing["cik"], filing["year"])

# 使用 LLM 提取风险
from src.llm.client import EdgarLLMClient

client = EdgarLLMClient()
result = client.extract_risks(section_1a, company_name="Apple")
```

## 项目结构

```
FinText-LLM/
├── src/
│   ├── data/
│   │   └── loader.py       # EDGAR filing 加载器
│   ├── llm/
│   │   └── client.py       # vLLM 风险提取客户端
│   └── utils/
│       └── download_edgar_2020.py
├── docker-compose.yml
├── pyproject.toml
└── README.md
```

## 许可证

本项目包含来自 Yahoo Finance 的数据，遵循 ODC-BY 许可证。
