# V16 Spec 04 - Structured Report 与 Risk Scoring

## 目标

将报告生成从“直接生成 markdown”升级为：

```text
Risk scoring by deterministic formula
→ Structured RiskReport model
→ Guardrail validation
→ Markdown / frontend rendering
```

## 修改点

### RiskScore 输出范围

第 16 版建议 final score 使用 0-100，便于前端展示。

```python
class RiskScore(BaseModel):
    risk_id: str
    base_severity: int = Field(ge=1, le=5)
    recent_signal_strength: float = Field(ge=0, le=1)
    evidence_quality: float = Field(ge=0, le=1)
    source_diversity: float = Field(ge=0, le=1)
    novelty_score: float = Field(ge=0, le=1)
    graph_centrality: float = Field(default=0.0, ge=0, le=1)
    final_score: float = Field(ge=0, le=100)
    score_breakdown: dict[str, float]
    score_reasoning: str
```

### Deterministic score formula

```python
final_score = round(
    20 * normalize(base_severity, 1, 5)
    + 20 * recent_signal_strength
    + 20 * evidence_quality
    + 15 * source_diversity
    + 15 * novelty_score
    + 10 * graph_centrality,
    2,
)
```

要求：

- LLM 不决定 final_score。
- LLM 或模板只解释 score_reasoning。
- score_breakdown 必须暴露给前端。

## Structured Report models

新增或升级：

```python
class RiskReportItem(BaseModel):
    risk_id: str
    title: str
    risk_type: str
    severity: int
    final_score: float
    summary: str
    supporting_claim_ids: list[str]
    supporting_evidence_ids: list[str]
    related_graph_insight_ids: list[str] = []


class RecentChange(BaseModel):
    change_id: str
    text: str
    supporting_evidence_ids: list[str]
    confidence: float


class EvidenceReference(BaseModel):
    evidence_id: str
    source_name: str
    source_url: str | None
    quote_or_summary: str
    source_quality_score: float


class RiskReport(BaseModel):
    title: str
    executive_summary: str
    top_risks: list[RiskReportItem]
    recent_changes: list[RecentChange]
    evidence_table: list[EvidenceReference]
    second_order_effects: list[GraphInsight]
    evidence_vs_inference: list[Claim]
    limitations: list[str]
    recommended_next_questions: list[str]
    disclaimer: str
    markdown: str | None = None
```

## Report requirements

必须包含：

- disclaimer。
- limitations。
- evidence_vs_inference。
- no direct buy/sell advice。
- every RiskReportItem has evidence ids。
- every claim has evidence ids unless explicitly hypothesis with low confidence。

## Markdown renderer

新增：

```text
src/reports/renderer.py
```

函数：

```python
def render_risk_report_markdown(report: RiskReport) -> str:
    ...
```

Markdown sections：

```markdown
# {title}

## Executive Summary
## Top Risks
## Recent Changes
## Evidence Table
## Second-Order Effects
## Evidence vs Inference
## Confidence & Limitations
## Recommended Next Research Questions
## Disclaimer
```

## Tests

新增：

```text
tests/workflows/test_risk_scoring.py
tests/reports/test_report_renderer.py
```

测试点：

- score formula deterministic。
- final_score range 0-100。
- score_breakdown contains all components。
- report without disclaimer fails guardrail。
- report markdown contains required sections。
- report item with missing evidence fails guardrail。

## 验收命令

```bash
uv run pytest tests/workflows/test_risk_scoring.py -q
uv run pytest tests/reports/test_report_renderer.py -q
```

