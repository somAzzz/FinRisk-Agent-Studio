# Step 03 - SEC API Client 与最新 Filing 获取

## 目标

接入 SEC 官方数据源，用于获取 2020 年以后最新 filing、公司 filing 历史和 XBRL company facts。

Hugging Face EDGAR corpus 适合历史语料，但生产研究需要最新 filing。

## 需要新增或修改的文件

新增：

```text
src/data/sec_client.py
src/data/filing_fetcher.py
src/data/xbrl.py
tests/data/test_sec_client.py
tests/data/test_filing_fetcher.py
tests/data/test_xbrl.py
```

修改：

```text
src/data/__init__.py
src/config.py
pyproject.toml
```

## SEC Client 设计

新增 `SECClient`：

```python
class SECClient:
    def __init__(
        self,
        user_agent: str | None = None,
        rate_limit_per_second: float | None = None,
        timeout: float = 20.0,
    ):
        ...

    def get_submissions(self, cik: str) -> dict:
        ...

    def get_company_facts(self, cik: str) -> dict:
        ...

    def get_filing_html(self, accession_number: str, cik: str, primary_doc: str) -> str:
        ...
```

要求：

- 所有请求必须带 `User-Agent`。
- 默认速率限制不超过 SEC fair access 要求。
- CIK 统一补零为 10 位。
- HTTP 错误应转换为自定义异常。
- 支持 retries，建议用 `tenacity`。

## FilingFetcher 设计

```python
class FilingFetcher:
    def __init__(self, sec_client: SECClient):
        ...

    def list_filings(
        self,
        cik: str,
        form_types: Sequence[str] = ("10-K", "10-Q", "8-K"),
        since: date | None = None,
        limit: int | None = None,
    ) -> list[FilingMetadata]:
        ...

    def fetch_filing(self, metadata: FilingMetadata) -> FilingRecord:
        ...
```

新增 schema 可放在 `src/schemas/filings.py`：

```python
class FilingMetadata(BaseModel):
    cik: str
    accession_number: str
    form_type: str
    filing_date: date
    report_date: date | None = None
    primary_document: str
    url: str
```

## Section Extraction

本步骤只需要做基础 HTML to text，不要求完美解析所有 item。

建议：

- 使用 BeautifulSoup 提取纯文本。
- 首先保留 `full_text` 到 `sections["full_text"]`。
- 如果已有可靠 section parser，再尝试抽取：
  - `section_1`
  - `section_1A`
  - `section_7`
  - `section_7A`
- 不要在本步骤做复杂 NLP。

如果 section parser 不稳定，允许先实现：

```python
sections = {"full_text": extracted_text}
```

并在 TODO 中标记后续增强。

## XBRL Company Facts

新增 `CompanyFactsClient` 或放在 `xbrl.py`：

```python
class CompanyFacts:
    cik: str
    facts: dict[str, Any]

def extract_metric(
    facts: dict,
    concept: str,
    unit: str = "USD",
) -> list[FactValue]:
    ...
```

优先支持：

- Revenue
- NetIncomeLoss
- Assets
- Liabilities
- OperatingIncomeLoss
- CapitalExpenditures，如可用

## 测试策略

默认测试 mock `httpx` 或 `requests`。

测试覆盖：

- CIK 补零。
- User-Agent 必填。
- submissions API response 解析。
- company facts response 解析。
- filing metadata URL 生成。
- HTTP 404/429/500 错误处理。
- rate limiter 被调用。

真实 SEC 集成测试必须加环境开关：

```bash
RUN_SEC_INTEGRATION=1 pytest tests/data/test_sec_client.py -m integration
```

## 验收标准

- 可以用 CIK 获取最近 10-K metadata。
- 可以获取 company facts JSON。
- 可以把最新 filing 转成 `FilingRecord`。
- 单元测试不依赖 SEC 网络。
- 速率限制和 User-Agent 明确存在。

## 给执行助手的注意事项

- 不要绕过 SEC fair access。
- 不要硬编码个人邮箱。
- 如果 API 结构和预期不同，以测试 fixture 为准实现最小可用能力。
- 不要把 filing section parser 做成巨型正则黑洞；先保证可维护。

