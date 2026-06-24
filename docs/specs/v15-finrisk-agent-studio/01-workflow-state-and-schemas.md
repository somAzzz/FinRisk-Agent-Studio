# Spec 01 - Workflow State 与 Pydantic Schemas

## 目标

建立 FinRisk Agent Studio 的统一数据契约。所有 workflow step、API、报告、评估和前端展示都应依赖这些 schema，而不是传递松散 dict。

## 范围

本 spec 只定义 schema 和基础测试，不接入真实 SEC、browser、LLM 或 Neo4j。

## 新增或修改文件

建议新增：

```text
src/workflows/__init__.py
src/workflows/state.py
src/schemas/finrisk.py
tests/workflows/test_workflow_schemas.py
```

如果项目已有相近 schema，应优先复用并补充字段，避免重复定义同名概念。

## 核心 schema

### `FinRiskRequest`

字段：

```python
class FinRiskRequest(BaseModel):
    ticker: str
    company_name: str | None = None
    analysis_goal: str
    time_horizon: str = "6-12 months"
    year: int | None = None
    sources: list[Literal["filing", "web", "transcript", "graph"]] = ["filing", "web", "graph"]
    max_browser_steps: int = Field(default=5, ge=0, le=20)
    demo_mode: bool = False
    cached_mode: bool = False
```

验收要求：

- `ticker` 自动转大写。
- `analysis_goal` 不能为空。
- `max_browser_steps` 不允许负数。
- `sources` 不能为空。

### `CompanyProfile`

字段：

```python
class CompanyProfile(BaseModel):
    company_name: str
    ticker: str
    cik: str | None = None
    filing_type: str | None = "10-K"
    analysis_year: int | None = None
    source: Literal["sec_company_tickers", "cache", "fixture", "manual", "unknown"] = "unknown"
    resolved_at: datetime
```

验收要求：

- ticker 大写。
- CIK 如果存在，格式应保留前导 0。
- `resolved_at` 使用 timezone-aware datetime。

### `ExtractedRisk`

字段：

```python
class ExtractedRisk(BaseModel):
    risk_id: str
    risk_type: Literal[
        "macro",
        "policy",
        "climate",
        "supply_chain",
        "competition",
        "regulatory",
        "technology",
        "geopolitical",
        "financial",
        "operational",
    ]
    risk_factor: str
    severity: int = Field(ge=1, le=5)
    evidence_quote: str
    source: str
    filing_section: str | None = None
    confidence: float = Field(ge=0, le=1)
```

验收要求：

- `severity` 超出 1-5 时校验失败。
- `evidence_quote` 不能为空。
- `confidence` 超出 0-1 时校验失败。

### `MarketEvidence`

字段：

```python
class MarketEvidence(BaseModel):
    evidence_id: str
    risk_id: str | None = None
    source_url: str
    source_title: str | None = None
    source_type: Literal["news", "financial", "regulatory", "company", "filing", "transcript", "other"]
    claim: str
    evidence_summary: str
    supports_risk: bool | None = None
    contradicts_risk: bool | None = None
    confidence: float = Field(ge=0, le=1)
    timestamp: datetime
```

验收要求：

- `source_url` 必须是可解析 URL，fixture 可使用 `https://example.com/...`。
- `timestamp` 使用 timezone-aware datetime。
- `claim` 和 `evidence_summary` 不能为空。

### `NormalizedEvidence`

字段：

```python
class NormalizedEvidence(BaseModel):
    evidence_id: str
    source_type: Literal["filing", "web", "transcript", "graph", "fixture"]
    source_name: str
    source_url: str | None = None
    quote: str | None = None
    summary: str
    related_risk_ids: list[str] = []
    credibility_score: float = Field(ge=0, le=1)
    collected_at: datetime
```

用途：

- 统一 filing、web、transcript、graph evidence。
- 作为 report、evaluation 和 graph 的共同输入。

### `RiskScore`

字段：

```python
class RiskScore(BaseModel):
    risk_id: str
    base_severity: int = Field(ge=1, le=5)
    recent_signal_strength: float = Field(ge=0, le=1)
    evidence_quality: float = Field(ge=0, le=1)
    source_diversity: float = Field(ge=0, le=1)
    novelty_score: float = Field(ge=0, le=1)
    graph_centrality: float | None = Field(default=None, ge=0, le=1)
    final_score: float = Field(ge=0, le=1)
    score_reasoning: str
```

要求：

- `final_score` 不由 LLM 直接生成，应由代码计算。
- `score_reasoning` 可由模板或 LLM 生成。

### `GraphInsight`

字段：

```python
class GraphInsight(BaseModel):
    insight_id: str
    source_company: str
    affected_entity: str
    risk_path: list[str]
    investment_theme: str | None = None
    supporting_evidence_ids: list[str]
    confidence: float = Field(ge=0, le=1)
```

验收要求：

- `risk_path` 至少包含 2 个节点。
- `supporting_evidence_ids` 不能为空，除非 demo fixture 明确标记为 synthetic。

### `RiskReport`

字段：

```python
class RiskReport(BaseModel):
    title: str
    executive_summary: str
    top_risks: list[ExtractedRisk]
    risk_scores: list[RiskScore]
    evidence_table: list[NormalizedEvidence]
    graph_insights: list[GraphInsight]
    evidence_vs_inference: str
    limitations: str
    recommended_next_questions: list[str]
    markdown: str
```

验收要求：

- `limitations` 必须存在。
- `evidence_vs_inference` 必须存在。
- `top_risks` 中每条 risk 必须能在 evidence table 找到相关 evidence。

### `WorkflowTraceEvent`

字段：

```python
class WorkflowTraceEvent(BaseModel):
    step_name: str
    status: Literal["pending", "running", "completed", "failed", "skipped"]
    started_at: datetime
    completed_at: datetime | None = None
    input_summary: str | None = None
    output_summary: str | None = None
    error: str | None = None
    retry_count: int = 0
```

### `WorkflowEvaluation`

字段：

```python
class WorkflowEvaluation(BaseModel):
    schema_valid: bool
    has_evidence_for_each_risk: bool
    unsupported_claims: list[str]
    financial_advice_risk: bool
    source_diversity_score: float = Field(ge=0, le=1)
    hallucination_risk_score: float = Field(ge=0, le=1)
    final_status: Literal["pass", "needs_review", "fail"]
```

### `FinRiskWorkflowState`

字段：

```python
class FinRiskWorkflowState(BaseModel):
    run_id: str
    request: FinRiskRequest
    company: CompanyProfile | None = None
    filing_risks: list[ExtractedRisk] = []
    market_evidence: list[MarketEvidence] = []
    normalized_evidence: list[NormalizedEvidence] = []
    risk_scores: list[RiskScore] = []
    graph_insights: list[GraphInsight] = []
    report: RiskReport | None = None
    evaluation: WorkflowEvaluation | None = None
    trace: list[WorkflowTraceEvent] = []
    status: Literal["created", "running", "completed", "failed", "needs_review"] = "created"
```

## 实现步骤

1. 新建 `src/schemas/finrisk.py`。
2. 定义上述 schema。
3. 使用 `datetime.now(timezone.utc)`，避免 `datetime.utcnow()`。
4. 在 `src/workflows/state.py` re-export workflow state，方便后续 step 引用。
5. 增加 schema validation tests。

## 单元测试要求

新增 `tests/workflows/test_workflow_schemas.py`，覆盖：

- request ticker normalization。
- severity 边界。
- confidence 边界。
- timezone-aware datetime。
- report 必填 sections。
- workflow state 可以 JSON serialize / deserialize。

## 验收命令

```bash
uv run pytest tests/workflows/test_workflow_schemas.py -q
uv run pytest -q
```

## 完成定义

- 所有 schema 可导入。
- 所有 schema 测试通过。
- 不需要真实外部服务。
- 不引入与现有 schema 冲突的重复概念。

