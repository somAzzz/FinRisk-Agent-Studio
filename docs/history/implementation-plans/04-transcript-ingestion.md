# Step 04 - 电话会议 Transcript 接入

## 目标

建立统一 transcript provider 抽象，优先接入一个免费或低成本 provider，同时支持后续接入付费 provider。

电话会议是管理层情绪、机会发现和风险验证的核心数据源。

## 需要新增或修改的文件

新增：

```text
src/data/transcripts.py
src/data/providers/__init__.py
src/data/providers/alpha_vantage.py
src/data/providers/defeatbeta.py   # 2026-06-25: free, no-API-key provider
src/data/providers/fmp.py
tests/data/test_transcripts.py
tests/data/providers/test_alpha_vantage.py
tests/data/providers/test_defeatbeta.py
tests/data/providers/test_fmp.py
```

修改：

```text
src/data/__init__.py
src/config.py
src/pipelines/analyze_company.py   # dispatcher now tries defeatbeta first
pyproject.toml
```

## Provider 抽象

```python
class TranscriptProvider(Protocol):
    provider_name: str

    def list_transcripts(self, ticker: str) -> list[TranscriptMeta]:
        ...

    def get_transcript(
        self,
        ticker: str,
        year: int,
        quarter: int,
    ) -> Transcript:
        ...
```

新增 schema：

```python
class TranscriptMeta(BaseModel):
    ticker: str
    year: int
    quarter: int
    provider: str
    title: str | None = None
    published_at: datetime | None = None
    transcript_id: str | None = None
    url: str | None = None
```

`Transcript` 和 `TranscriptTurn` 应使用 Step 01 中的 schema。

## Alpha Vantage Provider

环境变量：

```text
ALPHA_VANTAGE_API_KEY
```

职责：

- 根据 ticker/year/quarter 获取 transcript。
- 将 provider 原始格式转成统一 `Transcript`。
- 如果 API 不支持 list，则可先返回空列表或基于最近季度尝试。

错误处理：

- 缺少 API key：抛出 `TranscriptProviderConfigError`。
- API limit：抛出 `TranscriptRateLimitError`。
- 没有 transcript：抛出 `TranscriptNotFoundError`。

## FMP Provider

环境变量：

```text
FMP_API_KEY
```

职责：

- 支持 search/list transcript。
- 支持获取指定 quarter transcript。
- 统一 speaker turn。

## Defeatbeta Provider (2026-06-25)

无 API key — 数据来自 HuggingFace parquet 镜像 `defeatbeta/yahoo-finance-data`，由 DuckDB + `cache_httpfs` 在本地缓存。已成为 `_load_transcripts_live` 的默认首选 provider（无 key 时仍可工作），FMP / Alpha Vantage 作为付费备选。

环境变量（可选）：

```text
DEFEATBETA_PROXY   # 仅在受限网络下设置 HTTP 代理
```

文件：`src/data/providers/defeatbeta.py`

提供：

- `DefeatBetaProvider` — 实现 `TranscriptProvider` Protocol（duck-type）。`list_transcripts(ticker)` 调 `ticker.earning_call_transcripts().get_transcripts_list()`，返回 80+ 历史季度的 metadata。`get_transcript(ticker, year, quarter)` 调 `.get_transcript(year, quarter)` 返回 paragraph-level DataFrame。
- `fetch_filings_catalog_defeatbeta(ticker, form_types, since, limit)` — 用 defeatbeta 的 `sec_filing()` 给 FilingMetadata 列表（仅 catalog，不含 body）。
- `fetch_financial_metrics_defeatbeta(ticker)` — 最新一期 TTM PE / PS / PB / PEG / ROE / ROIC / Debt-to-Equity 比率字典。
- `fetch_revenue_breakdown_defeatbeta(ticker, breakdown, period_type)` — long-format 分部收入数据。**注**：defeatbeta 0.0.48 的 `revenue_by_segment/geography/product` 有 binder bug，此函数在受影响版本上返回 `[]`。

依赖安装：`pyproject.toml` 已声明 `defeatbeta-api>=0.0.47`，首次调用会触发 DuckDB 引导 (~10s)。

## Transcript Parsing

无论 provider 原文格式如何，都应转换成 turns：

```python
TranscriptTurn(
    speaker="Tim Cook",
    role="ceo",
    text="...",
    section="prepared_remarks",
    turn_index=0,
)
```

角色识别规则：

- speaker 包含 CEO、Chief Executive Officer -> `ceo`
- speaker 包含 CFO、Chief Financial Officer -> `cfo`
- speaker 包含 Analyst、Analyst - Company -> `analyst`
- Operator -> `operator`
- 其它 -> `unknown`

section 识别规则：

- 在 "Question-and-Answer Session" 之前为 `prepared_remarks`
- 之后为 `qa`
- 无法判断为 `unknown`

## Transcript Cache

本步骤可先实现简单文件缓存：

```text
.cache/fintext_llm/transcripts/<provider>/<ticker>/<year>Q<quarter>.json
```

要求：

- provider 可选择启用或禁用 cache。
- cache 存统一 `Transcript` JSON。
- 后续 pipeline 默认先查 cache。

## 测试策略

默认测试 mock API response。

测试覆盖：

- provider 缺 key 报错。
- response 转 `Transcript`。
- speaker role 识别。
- prepared remarks / Q&A 分段。
- cache read/write。
- not found 和 rate limit 处理。

集成测试：

```bash
RUN_TRANSCRIPT_INTEGRATION=1 pytest tests/data/providers -m integration
```

## 验收标准

- 至少实现一个可用 provider，推荐先实现 FMP 或 Alpha Vantage。
- 可以获取 `ticker/year/quarter` 对应 transcript。
- 输出统一 `Transcript` schema。
- 单元测试不访问真实 API。

## 后续步骤依赖

- Step 07 会从 transcript 抽取供应链、需求、margin、capex 信号。
- Step 09 会使用 transcript 做管理层情绪分析。

