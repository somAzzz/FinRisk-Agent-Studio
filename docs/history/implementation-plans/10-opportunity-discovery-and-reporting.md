# Step 10 - 机会发现与研究报告生成

## 目标

在供应链图、风险分析、管理层情绪和网页 evidence 的基础上，生成潜在投资研究假设。

注意：输出是 research hypothesis，不是投资建议。

## 需要新增或修改的文件

新增：

```text
src/agents/opportunity_agent.py
src/agents/report_agent.py
src/pipelines/discover_opportunities.py
src/pipelines/generate_report.py
src/schemas/hypotheses.py
tests/agents/test_opportunity_agent.py
tests/pipelines/test_discover_opportunities.py
tests/pipelines/test_generate_report.py
```

## Hypothesis Schema

```python
class InvestmentHypothesis(BaseModel):
    hypothesis_id: str
    title: str
    hypothesis_type: Literal[
        "supply_chain_opportunity",
        "policy_beneficiary",
        "sentiment_turnaround",
        "geopolitical_substitution",
        "risk_mispricing",
        "demand_acceleration",
    ]
    statement: str
    companies: list[Entity]
    graph_paths: list[list[Entity]] = Field(default_factory=list)
    supporting_claims: list[Claim]
    evidence: list[Evidence]
    counter_evidence: list[Evidence] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    watchlist_triggers: list[str] = Field(default_factory=list)
    risks_to_monitor: list[str] = Field(default_factory=list)
    not_investment_advice: bool = True
```

## Opportunity Agent

输入：

- 公司实体
- 供应链图路径
- risk claims
- sentiment result
- policy exposure
- geopolitical exposure
- web evidence

输出：

- 3-5 条高质量 hypothesis
- 每条至少 2 条 supporting evidence
- 每条至少 1 条 risk_to_monitor
- confidence 不得超过 evidence 质量允许范围

## 机会类型规则

### Supply Chain Opportunity

条件：

- 下游需求增长 evidence
- 图中存在上游供应商或替代供应商
- 网页或 filing 有订单、产能、价格、客户关系证据

### Policy Beneficiary

条件：

- policy exposure 为 beneficiary
- 公司产品或 segment 与政策目标匹配
- 有 filing/transcript/web evidence 支撑

### Sentiment Turnaround

条件：

- 最近 transcript 情绪改善
- demand/guidance/margin 中至少一个主题改善
- 风险因素没有明显恶化

### Geopolitical Substitution

条件：

- 某区域风险上升
- 图中存在替代供应商或替代地区
- 新闻或 filing 支持 reshoring/localization

### Risk Mispricing

条件：

- 公司持续披露风险，但 web evidence 显示风险升温或缓解
- 或市场 narrative 与 filing evidence 存在差异

## Report Agent

输出 Markdown 报告：

```text
# Company Research Brief: <Ticker>

## Executive Summary

## Key Evidence

## Supply Chain Map

## Management Sentiment

## Policy and Geopolitical Exposure

## Opportunity Hypotheses

## Risks and Counter-Evidence

## Watchlist Triggers

## Sources

Disclaimer: This report is for research only and is not investment advice.
```

报告要求：

- 每条结论必须引用 evidence。
- 不允许没有证据的断言。
- 明确展示 counter-evidence。
- 明确加免责声明。

## Pipeline

```python
def discover_opportunities(
    ticker: str,
    graph_client: Neo4jClient,
    claims: list[Claim],
    evidence: list[Evidence],
) -> list[InvestmentHypothesis]:
    ...
```

```python
def generate_company_report(
    ticker: str,
    hypotheses: list[InvestmentHypothesis],
    claims: list[Claim],
    evidence: list[Evidence],
) -> str:
    ...
```

## 测试策略

使用 mock graph paths 和 claims。

测试覆盖：

- hypothesis 必须有 evidence。
- confidence 边界。
- report 包含 disclaimer。
- report 不包含无 evidence claim。
- counter_evidence 会显示。

## 验收标准

- 可以用 mock 数据生成 3 条 hypothesis。
- 可以生成 Markdown 报告。
- 报告所有 claim 都有证据引用。

## 给执行助手的注意事项

- 避免确定性语言，例如“必然上涨”“强烈买入”。
- 使用“可能受益”“值得跟踪”“研究假设”等表述。
- 这个模块应依赖 Claim/Evidence/Graph，而不是直接重读所有原文。

