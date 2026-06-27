# 03 - Data Tools: SEC, Transcript, Financials

## 目标

把 roadmap 中的 filing、transcript、financial metrics 能力包装为 LLM-visible read tools。

第一批数据工具：

- `sec_list_filings`
- `sec_fetch_filing`
- `transcript_lookup`
- `financial_metrics_lookup`
- `xbrl_fact_lookup`

这些工具只读，不写 DB、不写 graph。

## sec_list_filings

### 用途

LLM 想知道某公司有哪些最新 filing。

### 参数

```json
{
  "ticker": "AAPL",
  "form_types": ["10-K", "10-Q"],
  "limit": 5,
  "since": "2024-01-01"
}
```

### 后端

优先复用：

- `src/data/ticker_resolver.py`
- `src/data/filing_fetcher.py`
- SEC submissions API。

### 输出

```json
{
  "ticker": "AAPL",
  "filings": [
    {
      "accession_number": "...",
      "form_type": "10-K",
      "filed_at": "...",
      "primary_document_url": "..."
    }
  ]
}
```

## sec_fetch_filing

### 用途

LLM 选择一个 filing 后，后端抓取全文或指定 section。

### 参数

```json
{
  "ticker": "AAPL",
  "accession_number": "...",
  "section": "1A"
}
```

### 输出

```json
{
  "ticker": "AAPL",
  "accession_number": "...",
  "section": "1A",
  "text": "...",
  "source_url": "...",
  "evidence_candidates": []
}
```

### 限制

- 默认不返回完整超长 filing。
- section 参数必须白名单。
- 内容超过预算时裁剪并标记。

## transcript_lookup

### 用途

查询电话会议 transcript，用于管理层情绪、需求、供应链、guidance 分析。

### 参数

```json
{
  "ticker": "NVDA",
  "year": 2025,
  "quarter": 1,
  "section": "qa"
}
```

### 后端

复用：

- `src/data/transcripts.py`
- `src/data/providers/alpha_vantage.py`
- `src/data/providers/fmp.py`

### 输出

```json
{
  "ticker": "NVDA",
  "year": 2025,
  "quarter": 1,
  "sections": [],
  "speakers": [],
  "evidence_candidates": []
}
```

## financial_metrics_lookup

### 用途

查询 ratios / financial metrics，让 LLM 能把文本线索和财务事实对齐。

### 参数

```json
{
  "ticker": "MSFT",
  "metrics": ["revenue", "gross_margin", "capex"],
  "period": "annual",
  "years": [2023, 2024, 2025]
}
```

### 后端

复用：

- `src/data/providers/defeatbeta.py`
- `src/data/providers/fmp.py`
- `src/data/providers/alpha_vantage.py`
- `src/data/xbrl.py`

### 输出

```json
{
  "ticker": "MSFT",
  "metrics": [
    {"name": "revenue", "period": "2025", "value": 123, "unit": "USD"}
  ],
  "source": "xbrl"
}
```

## xbrl_fact_lookup

### 用途

针对 SEC Company Facts 获取标准化 facts。

### 参数

```json
{
  "ticker": "AAPL",
  "concepts": ["Revenues", "GrossProfit"],
  "period": "annual",
  "limit": 5
}
```

## ToolCatalog scope

这些工具不进入默认 general catalog，按 scope 暴露：

| scope | tools |
|---|---|
| `finrisk_filing` | `sec_list_filings`, `sec_fetch_filing`, `xbrl_fact_lookup` |
| `transcript_analysis` | `transcript_lookup` |
| `supply_chain` | `web_search`, `web_fetch`, `transcript_lookup`, `financial_metrics_lookup` |
| `company_research` | 全部 read-only tools |

## 测试

新增：

```text
tests/tools/test_data_tool_catalog.py
```

覆盖：

- 无真实 API key 时工具返回可解释错误或 empty result。
- mock SEC client 下 `sec_list_filings` 输出 JSON。
- mock filing fetcher 下 `sec_fetch_filing` 支持 section 裁剪。
- mock transcript provider 下 transcript lookup 可转 evidence。
- financial metrics 输出 JSON-serializable。

## 验收

```bash
uv run pytest tests/tools/test_data_tool_catalog.py -q
```
