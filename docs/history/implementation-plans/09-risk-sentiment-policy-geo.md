# Step 09 - 管理层情绪、政策风险和地缘政治风险分析

## 目标

在已有实体、关系和 evidence 的基础上，增加三个分析 Agent：

- 管理层情绪分析
- 政策风险和政策机会分析
- 地缘政治风险分析

## 需要新增或修改的文件

新增：

```text
src/agents/sentiment_agent.py
src/agents/policy_geo_agent.py
src/agents/risk_agent.py
src/pipelines/analyze_risks.py
src/pipelines/analyze_sentiment.py
tests/agents/test_sentiment_agent.py
tests/agents/test_policy_geo_agent.py
tests/agents/test_risk_agent.py
```

可选新增：

```text
src/schemas/analysis.py
```

## 管理层情绪分析

输入：

- `Transcript`
- MD&A section
- historical transcript summaries，可后续实现

输出 schema：

```python
class TopicSentiment(BaseModel):
    topic: Literal[
        "demand",
        "margin",
        "supply_chain",
        "capex",
        "guidance",
        "competition",
        "policy",
        "geopolitics",
    ]
    sentiment: Literal["positive", "neutral", "negative", "mixed", "unclear"]
    confidence: float
    evidence: list[Evidence]

class ManagementSentimentResult(BaseModel):
    overall_tone: Literal["positive", "neutral", "negative", "mixed"]
    uncertainty: float = Field(ge=0.0, le=1.0)
    defensiveness: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    guidance_signal: Literal["raised", "lowered", "maintained", "unclear"]
    topic_sentiment: list[TopicSentiment]
    claims: list[Claim]
```

规则：

- Analyst question 不能单独作为管理层观点。
- Management answer 可以作为观点。
- 如果 prepared remarks 乐观而 Q&A 防御，应生成 mixed claim。
- 所有 topic sentiment 必须带 evidence。

## 政策风险和政策机会

覆盖主题：

- IRA
- CHIPS Act
- tariffs
- export controls
- carbon regulation
- defense spending
- healthcare regulation
- antitrust
- tax policy
- reshoring / localization

输出 schema：

```python
class PolicyExposure(BaseModel):
    policy_name: str
    exposure_type: Literal["beneficiary", "risk", "mixed", "unknown"]
    affected_segments: list[str] = Field(default_factory=list)
    time_horizon: Literal["short", "mid", "long", "unknown"]
    confidence: float
    evidence: list[Evidence]
    claims: list[Claim]
```

分析来源：

- Filing risk factors
- Business description
- MD&A
- Transcript
- Web search

## 地缘政治风险

风险类型：

- sanction
- export_control
- conflict
- tariff
- supply_disruption
- shipping_disruption
- commodity_shock
- localization_requirement

输出 schema：

```python
class GeopoliticalExposure(BaseModel):
    risk_type: str
    region: str
    impacted_entities: list[Entity]
    supply_chain_paths: list[list[Entity]] = Field(default_factory=list)
    risk_score: float = Field(ge=0.0, le=1.0)
    opportunity_offset: list[Claim] = Field(default_factory=list)
    evidence: list[Evidence]
```

## Risk Agent

职责：

- 汇总 filing、transcript、web 中的风险 claim。
- 分类：
  - macro
  - policy
  - geopolitical
  - supply_chain
  - customer_concentration
  - margin
  - legal
  - market
- 输出风险评分和 evidence。

```python
class RiskAssessment(BaseModel):
    company: Entity
    risks: list[Claim]
    overall_risk_score: float
    top_risk_categories: list[str]
    evidence: list[Evidence]
```

## Pipeline

```python
def analyze_company_risks(
    ticker: str,
    filings: list[FilingRecord],
    transcripts: list[Transcript],
    web_evidence: list[Evidence],
) -> RiskAssessment:
    ...
```

```python
def analyze_management_sentiment(
    ticker: str,
    transcripts: list[Transcript],
    mda_sections: list[str],
) -> ManagementSentimentResult:
    ...
```

## 测试策略

使用固定 transcript 和 filing snippet。

测试覆盖：

- prepared remarks 与 Q&A 分别识别。
- analyst question 不被误判为公司观点。
- policy exposure 必须带 evidence。
- geopolitical exposure risk_score 在 0 到 1。
- no evidence claim 被 critic 降级。

## 验收标准

- 可以对 mock transcript 输出管理层情绪。
- 可以对 mock filing 输出政策/地缘风险。
- 所有输出可转成 Claim 并写入图数据库。

## 给执行助手的注意事项

- 不要把 sentiment 做成简单词典匹配，初版可规则 + LLM 混合。
- 不要输出“投资建议”，只输出风险和研究信号。
- 地缘政治风险要区分直接风险和供应链传导风险。

