# Step 16 - Quality Layer 与 Graph Reasoning 核心化路线

## 目标

本文件是在 Step 15 的基础上做的第 16 版规划。Step 15 已经把项目重新组织为 `FinRisk Agent Studio`，但仍有两个问题：

- Evaluation / Guardrails 还偏向最后验收项，没有成为贯穿 workflow 的质量层。
- Graph Reasoning 还偏向一个普通 step，没有体现图查询、路径排序、证据绑定、LLM 解释和可视化校验的组合能力。

第 16 版的核心调整：

> Evaluation / Guardrails 是横跨每一步的 Quality Layer，不是最后一个 Step。

> Graph Reasoning 不是“把图给 LLM 看”，而是 Graph Query、Path Ranking、Evidence Binding、LLM Explanation、Visual Validation 的组合。

## 新架构总览

```text
FinRisk Agent Studio

Input
  ↓
Pydantic Workflow Runtime
  ↓
Company Resolver
  ↘ pre/post step guardrails
Filing Risk Extractor
  ↘ schema/evidence guardrails
Market Evidence Collector
  ↘ source/evidence guardrails
Evidence Normalizer
  ↘ claim/evidence contract guardrails
Risk Scorer
  ↘ score formula guardrails
Graph Reasoner
  ↘ graph path guardrails
Structured Report Generator
  ↘ report/financial safety guardrails
Human Review Gate
  ↓
Dashboard
  - Timeline
  - Risk Report
  - Evidence Graph
  - Evaluation
```

## 与 Step 15 的关系

Step 15 保留：

- FinRisk Agent Studio 产品定位。
- Pydantic-first custom workflow。
- cached demo mode。
- FastAPI。
- 前端 dashboard。
- local LLM / API provider 双模式。

Step 16 修改：

- 把原来的 `Evaluation & Guardrails` 从第 8 个 step 改成横向 `Quality Layer`。
- 保留最终 global evaluation，但它只做汇总和 human review gate。
- 把 `GraphReasonerStep` 拆成内部 5 阶段。
- 把 `RiskReport` 改为结构化 report model，再渲染 markdown/html。
- 将 `investment_theme` 改为 `research_theme`，降低金融建议风险。
- 前端增加独立 `Evaluation` tab，不只显示 pass/needs_review。

## 最新 workflow

外部 workflow 仍保持简洁：

```text
Company Resolver
→ Filing Risk Extractor
→ Market Evidence Collector
→ Evidence Normalizer
→ Risk Scorer
→ Graph Reasoner
→ Structured Report Generator
→ Human Review Gate
```

每一步实际执行变成：

```text
Pre-step validation
→ Step execution
→ Post-step validation
→ State update
→ Trace update
→ Optional gate / fallback
```

示意：

```python
async def run_step(
    state: FinRiskWorkflowState,
    step_name: str,
    step_fn: Callable,
    validators: list[Validator],
) -> FinRiskWorkflowState:
    trace_start(state, step_name)

    pre_eval = guardrail_engine.validate_pre_step(step_name, state)
    state.add_evaluation(pre_eval)
    if pre_eval.has_blocker:
        return state.block(step_name, pre_eval)

    output = await step_fn(state)

    post_eval = guardrail_engine.validate_post_step(
        step_name=step_name,
        output=output,
        state=state,
        validators=validators,
    )
    state.add_evaluation(post_eval)
    if post_eval.has_blocker:
        return state.block(step_name, post_eval)

    state = apply_output(state, step_name, output)
    trace_end(state, step_name)
    return state
```

## Quality Layer 设计

## 四层 Guardrails

```text
Layer 1: Schema & Contract Guardrails
Layer 2: Evidence & Grounding Guardrails
Layer 3: Domain & Financial Safety Guardrails
Layer 4: Workflow Quality & Regression Evaluation
```

### Layer 1：Schema & Contract Guardrails

目标：

- 保证每一步输出符合 Pydantic contract。
- 保证 ID 引用合法。
- 保证分数、枚举、时间戳合法。

核心检查：

- `schema_valid`
- `required_fields_present`
- `enum_value_valid`
- `id_reference_valid`
- `score_range_valid`
- `timestamp_valid`

阻断级别：

- schema invalid：blocker
- ID 引用错误：blocker
- score 越界：blocker
- timestamp 缺失：warning 或 error

### Layer 2：Evidence & Grounding Guardrails

目标：

- 保证每个风险、claim、graph insight 都有证据支撑。
- 防止空泛证据进入报告。

核心检查：

- `risk_has_filing_evidence`
- `market_evidence_has_source_url`
- `claim_has_supporting_evidence`
- `evidence_quote_min_length`
- `evidence_source_reachable_or_cached`
- `evidence_not_empty_or_generic`
- `claim_grounding_score`

Claim grounding 三层：

```text
规则检查
→ lexical/embedding overlap
→ optional LLM/NLI judge
```

LLM judge 只能给出判断，不能单独决定最终 pass/fail。

### Layer 3：Domain & Financial Safety Guardrails

目标：

- 防止金融风险分析变成买卖建议。
- 保证报告把 analysis、hypothesis、recommendation 边界说清楚。

核心检查：

- `no_direct_buy_sell_advice`
- `no_guaranteed_return`
- `no_price_target_as_advice`
- `report_has_disclaimer`
- `separate_analysis_from_recommendation`

要求：

- 报告必须包含 disclaimer。
- 允许 recommended research questions。
- 不允许直接 trade action。

### Layer 4：Workflow Quality & Regression Evaluation

目标：

- 展示工程鲁棒性。
- 让 demo 能解释 fallback、latency、retry、缓存使用情况。

核心指标：

- workflow completion rate
- step retry count
- browser failure fallback used
- LLM fallback used
- cached mode used
- latency per step
- token/cost estimate

## Evaluation 数据结构

第 16 版不再使用过于扁平的 `WorkflowEvaluation`。

建议新增：

```python
class GuardrailSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    BLOCKER = "blocker"


class GuardrailStatus(str, Enum):
    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"
    NEEDS_REVIEW = "needs_review"


class GuardrailFinding(BaseModel):
    finding_id: str
    step_name: str
    check_name: str
    status: GuardrailStatus
    severity: GuardrailSeverity
    message: str
    affected_object_type: Literal[
        "risk",
        "evidence",
        "claim",
        "source",
        "graph_path",
        "report_section",
        "workflow",
    ]
    affected_object_id: str | None = None
    recommendation: str | None = None


class StepEvaluation(BaseModel):
    step_name: str
    status: GuardrailStatus
    findings: list[GuardrailFinding]
    metrics: dict[str, float] = {}
    latency_ms: int | None = None


class WorkflowEvaluation(BaseModel):
    run_id: str
    final_status: GuardrailStatus
    step_evaluations: list[StepEvaluation]
    overall_metrics: dict[str, float]
    blocker_count: int
    warning_count: int
    unsupported_claims: list[str]
    human_review_required: bool
```

## Workflow State 升级

建议将 state 扩展为：

```python
class FinRiskWorkflowState(BaseModel):
    request: FinRiskRequest
    run_id: str
    status: WorkflowStatus

    company: CompanyProfile | None = None
    filing_risks: list[ExtractedRisk] = []
    market_evidence: list[MarketEvidence] = []
    normalized_evidence: list[NormalizedEvidence] = []
    claims: list[Claim] = []
    risk_scores: list[RiskScore] = []

    graph_context: GraphQueryContext | None = None
    graph_paths: list[CandidateGraphPath] = []
    graph_insights: list[GraphInsight] = []

    report: RiskReport | None = None
    evaluations: list[StepEvaluation] = []
    workflow_evaluation: WorkflowEvaluation | None = None
    guardrail_findings: list[GuardrailFinding] = []
    trace: list[WorkflowTraceEvent] = []

    artifacts: dict[str, str] = {}
    fallback_events: list[FallbackEvent] = []
```

新增重点：

- `claims`：报告必须先结构化为 claim，而不是直接 markdown。
- `graph_paths`：保存候选路径，不只保存 final insight。
- `evaluations`：每一步都有质量结果。
- `guardrail_findings`：前端直接展示。
- `fallback_events`：展示系统鲁棒性。
- `artifacts`：保存 report markdown、graph JSON、eval JSON、cached outputs。

## Graph Reasoning 子系统

## 核心原则

不要把整个 Neo4j 图丢给 LLM。

正确流程：

```text
LLM / rules 生成分析目标
→ Graph Query Planner 生成候选查询
→ Neo4j / fixture graph 执行查询
→ Candidate Path Retriever 返回路径
→ Path Scorer 排序
→ Evidence Binder 绑定证据
→ LLM Path Interpreter 解释 top paths
→ Graph Insight Validator 校验
→ Graph visualization 输出
```

LLM 的职责：

- 生成图查询意图。
- 对候选路径做解释。
- 生成 narrative。
- 提出下一步研究问题。
- 标记 hypothesis。

LLM 不允许：

- 编造不存在的路径。
- 生成无 evidence 的 final insight。
- 把 research theme 写成买卖建议。

## 图数据模型

### Node types

```text
Company
Ticker
Filing
Risk
Evidence
Claim
Supplier
Sector
Region
Policy
MacroFactor
Event
Opportunity
```

### Edge types

```text
COMPANY_HAS_FILING
FILING_MENTIONS_RISK
RISK_SUPPORTED_BY_EVIDENCE
EVIDENCE_SUPPORTS_CLAIM
COMPANY_DEPENDS_ON_SUPPLIER
SUPPLIER_LOCATED_IN_REGION
REGION_EXPOSED_TO_RISK
POLICY_AFFECTS_SECTOR
MACRO_FACTOR_AFFECTS_RISK
RISK_AFFECTS_COMPANY
RISK_CREATES_OPPORTUNITY
CLAIM_DERIVED_FROM_PATH
```

每条边必须携带：

```python
class GraphEdgeMetadata(BaseModel):
    source: str
    evidence_ids: list[str]
    confidence: float
    extraction_method: Literal["rule", "llm", "manual", "imported"]
    created_at: datetime
```

原则：

> 没有 evidence 的边，不能作为 final insight，只能作为 hypothesis。

## Graph Reasoner 内部五阶段

外部仍叫 `GraphReasonerStep`，内部拆为：

```text
Graph Context Builder
→ Candidate Path Retriever
→ Path Scorer
→ LLM Path Interpreter
→ Graph Insight Validator
```

### 1. Graph Context Builder

输入：

- company
- filing risks
- normalized evidence
- claims
- analysis goal

输出：

```python
class GraphQueryContext(BaseModel):
    company_id: str
    ticker: str
    risk_ids: list[str]
    focus_entities: list[str]
    focus_risk_types: list[str]
    max_hops: int = 3
    allowed_edge_types: list[str]
```

### 2. Candidate Path Retriever

用 Cypher 或 fixture graph 查询候选路径，不让 LLM 硬编路径。

输出：

```python
class CandidateGraphPath(BaseModel):
    path_id: str
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    path_text: str
    evidence_ids: list[str]
    hop_count: int
```

### 3. Path Scorer

建议公式：

```text
path_score =
  0.25 * evidence_coverage
  + 0.20 * min_edge_confidence
  + 0.20 * relevance_to_analysis_goal
  + 0.15 * source_quality
  + 0.10 * novelty
  + 0.10 * graph_centrality
  - 0.05 * hub_penalty
```

LLM 不直接选路径。

### 4. LLM Path Interpreter

只解释 top ranked paths。

输出：

```python
class GraphInsight(BaseModel):
    insight_id: str
    source_company: str
    insight_type: Literal[
        "second_order_risk",
        "supply_chain_exposure",
        "policy_transmission",
        "market_opportunity",
        "research_hypothesis",
    ]
    risk_path_ids: list[str]
    affected_entities: list[str]
    explanation: str
    evidence_ids: list[str]
    confidence: float
    uncertainty: str
    recommended_next_questions: list[str]
    research_theme: str | None = None
```

注意：

- 使用 `research_theme`，不要使用 `investment_theme`。
- `market_opportunity` 必须标记为 hypothesis 或 research question。

### 5. Graph Insight Validator

检查：

- path_id 是否存在。
- affected_entities 是否在 path nodes 中。
- evidence_ids 是否存在。
- confidence 是否不高于 path_score 太多。
- edge 是否都有 evidence。
- path length 是否在 2-4 hops。
- LLM 是否编造节点。

规则：

```python
if insight.confidence > max(path_scores) + 0.1:
    downgrade_confidence()
```

## Risk Scorer 升级

分数必须由代码计算。

建议公式：

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

输出范围改为 0-100，更适合前端展示。

LLM 只负责：

```text
explain_score_reasoning
```

不负责：

```text
decide_score
```

## Report Generator 升级

Report Generator 不直接生成 markdown。

流程：

```text
RiskReport Pydantic model
→ report guardrails
→ markdown renderer
→ frontend renderer
```

建议：

```python
class Claim(BaseModel):
    claim_id: str
    text: str
    claim_type: Literal["evidence", "inference", "hypothesis"]
    supporting_evidence_ids: list[str]
    confidence: float


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
```

## Market Evidence Collector 升级

证据获取优先级：

```text
1. Cached evidence
2. SearchRouter API / structured search
3. Browser exploration
```

新增：

```python
class EvidenceAcquisitionMode(str, Enum):
    CACHED = "cached"
    SEARCH = "search"
    BROWSER = "browser"
    MANUAL_FIXTURE = "manual_fixture"
```

要求：

- Market Explorer 输出不直接进入 report。
- 必须先进入 Evidence Normalizer。
- fallback_events 要记录 evidence acquisition mode。

## API 升级

Step 15 的 3 个接口保留，同时预留更细接口：

```text
POST /workflows/finrisk/run
GET  /workflows/{run_id}
GET  /workflows/{run_id}/trace
GET  /workflows/{run_id}/report
GET  /workflows/{run_id}/graph
GET  /workflows/{run_id}/evaluation
GET  /workflows/{run_id}/artifacts
```

MVP 可以先内部调用，但 API response schema 应按这些资源拆分。

## 前端升级

第 16 版前端从四视图升级为五个 tab：

```text
1. Launcher
2. Timeline
3. Risk Report
4. Evidence Graph
5. Evaluation
```

Evaluation tab 是 demo 的核心亮点，不应隐藏在 Timeline 中。

## Evaluation 前端组件

### 1. Evaluation Overview

展示：

```text
Final Status
Schema Validity
Evidence Coverage
Unsupported Claims
Financial Advice Risk
Graph Path Validity
Source Diversity
```

### 2. Step Quality Timeline

在 Agent Timeline 上叠加质量状态：

```text
Company Resolver        PASS
Filing Risk Extractor   PASS, 1 warning
Market Explorer         WARNING, cached fallback used
Evidence Normalizer     PASS
Risk Scorer             PASS
Graph Reasoner          NEEDS REVIEW, 2 weak paths
Report Generator        PASS
```

### 3. Claim-Evidence Matrix

展示：

```text
Claim | Type | Evidence | Grounding | Status
```

这是证明系统不是 chatbot 的关键视图。

### 4. Risk Score Breakdown

展示：

```text
Base severity
Recent signal strength
Evidence quality
Source diversity
Novelty
Graph centrality
Final score
```

### 5. Guardrail Findings Drawer

点击 warning 展开：

```text
Finding
Step
Affected object
Severity
Recommendation
```

## Evidence Graph 前端升级

图不只是普通节点图，要展示：

- path
- evidence
- LLM insight
- guardrail status

节点类型：

```text
Company
Risk
Evidence
Supplier
Region
Policy
Insight
```

边样式：

```text
solid edge      evidence-backed
dashed edge     hypothesis
red border      needs review
thick edge      high confidence
thin edge       low confidence
```

Report 与 Graph 联动：

- Report 中每个 claim 后面可以点击 `View evidence graph`。
- 点击后高亮 claim → evidence → path → insight。

## 新两周执行计划

### Day 1-2：Schema、Workflow State、Trace

定义：

- Risk
- Evidence
- Claim
- GraphPath
- GraphInsight
- GuardrailFinding
- StepEvaluation
- WorkflowState
- FallbackEvent

### Day 3-4：Cached MVP Workflow

用 fixture 跑通：

- AAPL cached filing
- cached evidence
- mock graph
- structured report
- runtime evaluation

不接真实 browser。

### Day 5-6：Evaluation / Guardrails Engine

必须完成：

- schema validator
- evidence validator
- financial safety validator
- graph path validator
- claim grounding validator v1

### Day 7-8：Graph Reasoning v1

用 mock graph / fixture Neo4j 完成：

- graph context builder
- candidate path retrieval
- path scoring
- LLM or template interpretation
- graph insight validation
- graph JSON output

### Day 9-10：FastAPI + Frontend

完成：

- launcher
- timeline
- report
- graph
- evaluation tab

### Day 11-12：接入真实模块

接入：

- TickerResolver
- FilingFetcher
- SearchRouter
- MarketExplorer optional
- Neo4j optional

### Day 13-14：Polish

完成：

- README
- demo script
- screenshots
- cached run
- CI tests

## Spec 拆分

第 16 版详细规格放在：

```text
docs/specs/v16-quality-graph/
```

包含：

- `00-index.md`
- `01-quality-layer-runtime.md`
- `02-claim-grounding-and-source-quality.md`
- `03-graph-reasoning-subsystem.md`
- `04-structured-report-and-risk-scoring.md`
- `05-api-and-frontend-quality-graph.md`
- `06-v16-demo-acceptance.md`

## 第 16 版完成定义

当以下流程稳定运行时，第 16 版完成：

```bash
uv run python -m src.workflows.finrisk_workflow \
  --ticker AAPL \
  --analysis-goal "Identify macro, policy and supply-chain risks that changed recently." \
  --demo-mode
```

并且输出包含：

- 每步 trace。
- 每步 StepEvaluation。
- guardrail findings。
- claim-evidence matrix。
- candidate graph paths。
- ranked graph paths。
- graph insights。
- structured report。
- markdown report。
- workflow evaluation。

前端必须能展示：

- Timeline。
- Risk Report。
- Evidence Graph。
- Evaluation tab。
- Claim-Evidence Matrix。
- Risk Score Breakdown。
- Guardrail Findings Drawer。

质量要求：

- 每个 top risk 有 evidence。
- 每个 claim 有 supporting evidence ids。
- graph insight 不引用不存在的 path。
- graph path 每条边有 evidence 或被标为 hypothesis。
- report 无直接买卖建议。
- report 有 disclaimer。
- fallback events 可见。
- cached demo 不依赖 GPU、API key、外网、Neo4j。
