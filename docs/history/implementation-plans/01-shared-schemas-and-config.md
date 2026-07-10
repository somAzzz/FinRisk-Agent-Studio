# Step 01 - 统一 Schema、配置和证据模型

## 目标

建立全项目共享的数据结构和配置系统，为后续数据接入、Agent、图数据库和分析模块提供统一契约。

这一步是所有后续步骤的基础，优先级最高。

## 需要新增或修改的文件

新增：

```text
src/schemas/__init__.py
src/schemas/evidence.py
src/schemas/entities.py
src/schemas/relations.py
src/schemas/claims.py
src/schemas/filings.py
src/schemas/transcripts.py
src/config.py
tests/schemas/test_evidence.py
tests/schemas/test_entities.py
tests/test_config.py
```

可选修改：

```text
src/data/loader.py
src/llm/client.py
```

## 核心 Schema

### Evidence

`Evidence` 是整个系统最重要的数据结构。所有抽取结果、图关系和研究结论都必须能追溯到证据。

建议字段：

```python
class Evidence(BaseModel):
    evidence_id: str
    source_type: Literal[
        "edgar_corpus",
        "sec_filing",
        "sec_xbrl",
        "transcript",
        "web",
        "browser",
        "manual",
    ]
    source_id: str
    title: str | None = None
    url: str | None = None
    section: str | None = None
    speaker: str | None = None
    quote: str
    retrieved_at: datetime
    published_at: datetime | None = None
    char_start: int | None = None
    char_end: int | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)
```

要求：

- `quote` 不应为空。
- `confidence` 限制在 0 到 1。
- `evidence_id` 可用稳定 hash 生成。
- `source_id` 对 filing 可为 accession number，对 Hugging Face 可为 dataset/config/split/row。

### Entity

建议实体类型：

```python
EntityType = Literal[
    "company",
    "product",
    "segment",
    "customer",
    "supplier",
    "competitor",
    "country",
    "region",
    "commodity",
    "policy",
    "risk",
    "opportunity",
    "executive",
    "event",
]
```

字段：

```python
class Entity(BaseModel):
    entity_id: str
    name: str
    entity_type: EntityType
    normalized_name: str
    ticker: str | None = None
    cik: str | None = None
    aliases: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    evidence: list[Evidence] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
```

### Relation

建议关系类型：

```python
RelationType = Literal[
    "supplies_to",
    "buys_from",
    "customer_of",
    "competitor_of",
    "has_segment",
    "sells_product",
    "depends_on",
    "exposed_to",
    "mentions_risk",
    "impacted_by",
    "benefits_from",
    "subsidiary_of",
    "supports_claim",
]
```

字段：

```python
class Relation(BaseModel):
    relation_id: str
    source: Entity
    target: Entity
    relation_type: RelationType
    direction: Literal["directed", "undirected"] = "directed"
    evidence: list[Evidence]
    confidence: float = Field(ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)
```

### Claim

```python
class Claim(BaseModel):
    claim_id: str
    claim_type: Literal[
        "risk",
        "opportunity",
        "sentiment",
        "policy_exposure",
        "geopolitical_exposure",
        "supply_chain",
        "financial_signal",
    ]
    statement: str
    entities: list[Entity] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)
    evidence: list[Evidence]
    confidence: float = Field(ge=0.0, le=1.0)
    counter_evidence: list[Evidence] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
```

### FilingRecord

```python
class FilingRecord(BaseModel):
    source: Literal["huggingface", "sec"]
    cik: str
    ticker: str | None = None
    company_name: str | None = None
    form_type: str = "10-K"
    year: int | None = None
    filing_date: date | None = None
    accession_number: str | None = None
    sections: dict[str, str] = Field(default_factory=dict)
    url: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
```

### Transcript

```python
class TranscriptTurn(BaseModel):
    speaker: str
    role: Literal["ceo", "cfo", "executive", "analyst", "operator", "unknown"]
    text: str
    section: Literal["prepared_remarks", "qa", "unknown"]
    turn_index: int

class Transcript(BaseModel):
    ticker: str
    company_name: str | None = None
    year: int
    quarter: int
    provider: str
    transcript_id: str
    title: str | None = None
    published_at: datetime | None = None
    turns: list[TranscriptTurn]
    url: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
```

## 配置系统

新增 `src/config.py`，使用 Pydantic Settings 或简单 dataclass。优先使用 `pydantic-settings`，如果不想新增依赖，可以先用 `os.environ`。

建议配置：

```python
class Settings(BaseSettings):
    sec_user_agent: str = "FinText-LLM contact@example.com"
    sec_rate_limit_per_second: float = 8.0
    openai_base_url: str = "http://localhost:30000/v1"
    openai_api_key: str = "EMPTY"
    llm_model: str = "Qwen/Qwen3.5-35B-A3B"
    hf_edgar_dataset: str = "eloukas/edgar-corpus"
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str | None = None
    cache_dir: Path = Path(".cache/fintext_llm")
```

## 实施任务

1. 创建 `src/schemas` 包。
2. 实现 `Evidence`、`Entity`、`Relation`、`Claim`、`FilingRecord`、`Transcript`。
3. 为 id 生成提供 helper：

```python
def stable_id(prefix: str, *parts: str) -> str:
    ...
```

4. 实现 `src/config.py`。
5. 更新 `pyproject.toml`，如使用 `pydantic-settings` 则加入依赖。
6. 写单元测试覆盖：
   - confidence 边界
   - 空 quote 拒绝
   - stable id 稳定
   - optional 字段默认值
   - settings 从环境变量读取

## 验收标准

- `python -m pytest tests/schemas tests/test_config.py` 通过。
- 所有 schema 可被 `model_dump()` 序列化。
- 所有 schema 可被 JSON round-trip。
- 不破坏现有测试。

## 给执行助手的注意事项

- 不要在这一步实现业务逻辑。
- 不要把 schema 写进各个模块里，必须集中到 `src/schemas`。
- Evidence 是后续所有模块的共同语言，字段要稳定。

