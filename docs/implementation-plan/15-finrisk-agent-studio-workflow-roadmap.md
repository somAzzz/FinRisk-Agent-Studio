# Step 15 - FinRisk Agent Studio 工作流化开发路线

## 目标

本文件基于当前项目状态和外部评审建议，重新规划 FinText-LLM 的下一阶段开发路线。

核心判断：

> 当前项目不需要推倒重来。它已经具备金融文本分析、SEC filing、网页探索、本地 LLM、Neo4j 和报告生成的基础。下一步的关键不是继续堆功能，而是把这些能力组织成一个可运行、可解释、可评估、可部署的 Agent Workflow 系统。

建议将项目的展示形态命名为：

```text
FinRisk Agent Studio
```

副标题：

```text
An AI-native financial risk intelligence workflow using local LLMs, structured outputs, browser exploration, EDGAR filings, and graph-based reasoning.
```

中文定位：

> 一个面向金融分析师的 Agent 工作流系统：自动读取 SEC 年报风险因素，结合实时网页探索、结构化证据、图谱推理和评估护栏，生成宏观风险、政策风险、供应链二阶影响和潜在投资机会简报。

## 为什么要调整路线

当前项目已经有很多模块：

- EDGAR / SEC filing 数据读取。
- Hugging Face EDGAR loader。
- SGLang / local LLM client。
- browser exploration。
- SearchRouter。
- transcript provider 抽象。
- risk / sentiment / opportunity / report agents。
- Neo4j graph writer/query。
- offline demo。
- 分步实施文档。

但这些模块目前更像一个工具库和 pipeline 集合。正式展示和后续开发需要把它们显式组织成：

```text
Company Selection
→ Filing Risk Extraction
→ Live Market Exploration
→ Evidence Normalization
→ Risk Scoring
→ Graph Reasoning
→ Report Generation
→ Evaluation / Guardrails
→ Human Review / Export
```

这条路线既保留 Step 13 / Step 14 的正式项目目标，也补上一个可以快速展示、快速验收、快速迭代的 Agent Workflow Demo。

## 新的产品形态

## Demo 名称

推荐使用：

```text
FinRisk Agent Studio
```

备选：

```text
FinRisk Workflow Copilot
FinRisk Intelligence Workflow
```

建议优先使用 `FinRisk Agent Studio`，因为它更像一个可展示产品，而不是单纯脚本或研究项目。

## Demo 场景

不要做泛泛的 “chat with financial documents”。第一版只做一个非常明确的场景：

```text
输入公司 ticker，自动生成公司风险情报简报。
```

示例输入：

```text
Company: Apple
Ticker: AAPL
Analysis Goal: Identify macro, policy and supply-chain risks that changed recently.
Time Horizon: next 6-12 months
```

系统自动执行：

```text
1. Company Resolver
2. Filing Risk Extractor
3. Market Explorer
4. Evidence Normalizer
5. Risk Scorer
6. Graph Reasoner
7. Report Generator
8. Evaluation & Guardrails
```

最终输出：

- Top risks。
- Severity score。
- Filing evidence。
- Recent market/news evidence。
- Affected suppliers / sectors。
- Confidence score。
- What changed recently。
- Analyst-style report。
- Evidence graph。
- Guardrail / evaluation result。

## 工作流总图

```text
User Request
   ↓
Company Resolver
   ↓
Filing Risk Extractor
   ↓
Market Explorer
   ↓
Evidence Normalizer
   ↓
Risk Scorer
   ↓
Graph Reasoner
   ↓
Report Generator
   ↓
Evaluation & Guardrails
   ↓
Human Review / Export
```

## Pydantic-first Workflow 设计

第一版不建议引入 LangGraph、Google ADK 或过重框架。当前项目已经大量使用 Pydantic，最适合采用 Pydantic-first custom workflow。

建议新增核心状态：

```python
class FinRiskWorkflowState(BaseModel):
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
```

建议工作流入口：

```python
async def run_finrisk_workflow(request: FinRiskRequest) -> FinRiskWorkflowState:
    state = FinRiskWorkflowState(request=request)

    state.company = await resolve_company(state)
    state.filing_risks = await extract_filing_risks(state)
    state.market_evidence = await explore_market_evidence(state)
    state.normalized_evidence = await normalize_evidence(state)
    state.risk_scores = await score_risks(state)
    state.graph_insights = await reason_over_graph(state)
    state.report = await generate_report(state)
    state.evaluation = await evaluate_report(state)

    return state
```

要求：

- 每一步都必须有明确 input/output schema。
- 每一步都必须写入 trace。
- 每一步失败都应返回结构化错误。
- demo 模式必须支持 cached evidence fallback。
- 所有最终 claim 必须有 evidence。

## Agent / Step 设计

## Step 1：Company Resolver

职责：

- 将 ticker / company name 解析成标准公司信息。
- 统一 ticker、CIK、company name。
- 记录 provenance。

输入：

```json
{
  "company": "Apple",
  "ticker": "AAPL",
  "year": 2024
}
```

输出：

```json
{
  "company_name": "Apple Inc.",
  "ticker": "AAPL",
  "cik": "0000320193",
  "filing_type": "10-K",
  "analysis_year": 2024,
  "source": "sec_company_tickers"
}
```

实现建议：

- 复用 `src/data/ticker_resolver.py`。
- 不需要 LLM。
- 失败时不允许静默 fallback 到错误公司。

## Step 2：Filing Risk Extractor

职责：

- 获取 10-K / 10-Q。
- 抽取 Item 1A 等风险相关 section。
- 使用 LLM 或规则提取结构化风险。

建议输出 schema：

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

实现建议：

- 复用 `src/data/filing_fetcher.py`。
- 复用 `src/data/sec_sections.py`。
- 复用现有 LLM client。
- 将已有 dict 风险结果升级成强类型 Pydantic model。

验收标准：

- 每个 risk 必须有 `evidence_quote`。
- `severity` 必须在 1-5。
- 没有 evidence 的 risk 不进入最终 report。

## Step 3：Market Explorer

职责：

- 围绕 filing 中抽取的风险进行定向网页探索。
- 不再泛泛搜索新闻，而是查找最近证据来支持、削弱或更新风险判断。

示例目标：

```text
Find recent evidence related to Apple's supply chain risk:
- semiconductor shortages
- China manufacturing exposure
- regulatory pressure
Only collect evidence from financial, regulatory, company or credible news sources.
```

建议输出 schema：

```python
class MarketEvidence(BaseModel):
    evidence_id: str
    risk_id: str
    source_url: str
    source_title: str | None = None
    source_type: Literal["news", "financial", "regulatory", "company", "filing", "other"]
    claim: str
    evidence_summary: str
    supports_risk: bool | None = None
    contradicts_risk: bool | None = None
    confidence: float = Field(ge=0, le=1)
    timestamp: datetime
```

实现建议：

- 复用 `MarketExplorer` / browser 模块。
- 复用 `SearchRouter` 作为低成本路径。
- browser exploration 失败时 fallback 到 cached search evidence。
- 增加 source credibility scoring。

## Step 4：Evidence Normalizer

职责：

- 将 filing risk、browser finding、search result、transcript snippet 统一为标准 evidence。
- 形成 evidence graph 的输入。

实现建议：

- 不需要 LLM。
- 主要做 schema 转换、source 归一化、去重和 ID 生成。
- 保留 evidence 与 risk / claim 的关系。

输出应区分：

- `evidence`：原始事实或可引用片段。
- `inference`：系统推理。
- `hypothesis`：低置信度研究假设。

## Step 5：Risk Scorer

职责：

- 综合 filing severity、近期证据强度、证据质量、来源可信度、新颖性、政策相关性和图谱中心性。
- 输出可解释分数。

建议 schema：

```python
class RiskScore(BaseModel):
    risk_id: str
    base_severity: int
    recent_signal_strength: float
    evidence_quality: float
    source_diversity: float
    novelty_score: float
    graph_centrality: float | None = None
    final_score: float
    score_reasoning: str
```

重要原则：

- 不让 LLM 直接决定最终分数。
- 分数由规则和可解释公式计算。
- LLM 可以生成自然语言解释，但不能覆盖结构化分数。

## Step 6：Graph Reasoner

职责：

- 基于 Neo4j 或内存图，发现供应链二阶影响和潜在投资方向。

示例：

```text
Apple
→ depends_on
TSMC
→ exposed_to
Taiwan geopolitical risk
```

建议输出 schema：

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

实现建议：

- 复用 `src/graph/writer.py` 和 `src/graph/queries.py`。
- 第一版允许用 mock graph / fixture graph 保证 demo 稳定。
- 后续切换到真实 Neo4j。

## Step 7：Report Generator

职责：

- 生成结构化风险情报简报。
- 明确区分 evidence、inference、hypothesis。

建议报告结构：

```markdown
# Apple Risk Intelligence Brief

## Executive Summary

## Top Risks

## Recent Changes

## Evidence Table

## Second-Order Effects

## Evidence vs Inference

## Confidence & Limitations

## Recommended Next Research Questions
```

要求：

- 报告不能包含无证据 claim。
- 报告不能输出直接买卖建议。
- 报告必须包含 limitations。
- 每个 top risk 必须引用 filing evidence 或 recent evidence。

## Step 8：Evaluation & Guardrails

职责：

- 在报告生成后进行代码级检查。
- 不把 guardrails 只写在 prompt 中。

建议 schema：

```python
class WorkflowEvaluation(BaseModel):
    schema_valid: bool
    has_evidence_for_each_risk: bool
    unsupported_claims: list[str]
    financial_advice_risk: bool
    source_diversity_score: float
    hallucination_risk_score: float
    final_status: Literal["pass", "needs_review", "fail"]
```

必须检查：

- risk severity 是否在 1-5。
- 每个 risk 是否有 evidence quote。
- 每个 claim 是否绑定 source。
- 是否出现 buy / sell / guaranteed return 等投资建议风险。
- report 是否区分 evidence、inference、hypothesis。
- source diversity 是否足够。

## 建议目录结构

为了减少对现有 `src/` 的大规模搬迁，第一阶段不建议直接重构成全新的 `backend/` 结构。

推荐渐进式结构：

```text
src/
├── workflows/
│   ├── finrisk_workflow.py
│   ├── state.py
│   └── steps/
│       ├── company_resolver.py
│       ├── filing_risk_extractor.py
│       ├── market_explorer_step.py
│       ├── evidence_normalizer.py
│       ├── risk_scorer.py
│       ├── graph_reasoner.py
│       ├── report_generator.py
│       └── evaluator.py
├── api/
│   ├── main.py
│   └── workflows.py
├── schemas/
├── data/
├── browser/
├── tools/
├── graph/
├── agents/
└── llm/
frontend/
eval/
docs/
scripts/
```

后续如果要做更正式的服务边界，再迁移到：

```text
backend/app/
frontend/
eval/
```

但当前优先目标是跑通 workflow，不是移动文件。

## API 设计

第一版 FastAPI 只需要三个接口：

```text
POST /workflows/finrisk/run
GET /workflows/{run_id}
GET /workflows/{run_id}/report
```

建议 request：

```python
class FinRiskRequest(BaseModel):
    ticker: str
    company_name: str | None = None
    analysis_goal: str
    time_horizon: str = "6-12 months"
    year: int | None = None
    sources: list[Literal["filing", "web", "transcript", "graph"]]
    max_browser_steps: int = 5
    demo_mode: bool = False
```

建议 response：

```python
class WorkflowRunSummary(BaseModel):
    run_id: str
    status: Literal["queued", "running", "completed", "failed", "needs_review"]
    current_step: str | None
    started_at: datetime
    completed_at: datetime | None
    report_url: str | None
```

## 前端设计

不需要复杂 UI。第一版只做 4 个页面或 4 个视图。

## 页面 1：Workflow Launcher

字段：

- Company / ticker。
- Analysis goal。
- Time horizon。
- Sources to use。
- Max browser steps。
- Demo mode / cached mode。

按钮：

```text
Run Risk Workflow
```

## 页面 2：Agent Timeline

展示：

```text
Company Resolver
Filing Risk Extractor
Market Explorer
Evidence Normalizer
Risk Scorer
Graph Reasoner
Report Generator
Evaluation
```

每一步展示：

- status。
- duration。
- input summary。
- output summary。
- errors。
- retry count。

## 页面 3：Risk Report

展示：

- top risks。
- severity。
- evidence quotes。
- recent findings。
- confidence。
- limitations。
- evidence vs inference。

## 页面 4：Evidence Graph

展示：

```text
Company → Risk → Evidence → Supplier / Policy / Market Factor
```

候选技术：

- ReactFlow。
- D3.js。
- Cytoscape.js。

第一版建议用 ReactFlow，因为它更适合流程和关系图展示。

## LLM Provider 策略

当前项目偏向本地 SGLang，这是优势，但 demo 不能只依赖高显存 GPU。

必须支持两种模式：

```text
local-llm mode:
SGLang + Qwen + Docker GPU

api mode:
OpenAI / Claude / Gemini / OpenAI-compatible endpoint
```

建议环境变量：

```text
LLM_PROVIDER=sglang
LLM_PROVIDER=openai
LLM_PROVIDER=gemini
LLM_PROVIDER=claude
LLM_BASE_URL=http://localhost:30000/v1
LLM_MODEL=Qwen/Qwen3.5-35B-A3B
```

要求：

- 所有 LLM client 输出都要走 Pydantic schema。
- API mode 用于轻量复现。
- local mode 用于展示本地 LLM 工程能力。
- demo mode 可使用 cached LLM output。

## Evaluation 设计

新增：

```text
eval/golden_cases.json
eval/run_eval.py
tests/workflows/test_guardrails.py
tests/workflows/test_workflow_contract.py
```

golden case 示例：

```json
[
  {
    "company": "Apple",
    "ticker": "AAPL",
    "input_risk": "supply chain concentration",
    "expected_risk_type": "supply_chain",
    "must_have_evidence": true,
    "should_not_contain": ["buy", "sell", "guaranteed return"]
  }
]
```

评估指标：

- schema valid rate。
- evidence coverage。
- unsupported claim count。
- financial advice risk count。
- source diversity score。
- hallucination risk score。
- workflow completion rate。

## 开发路线

## Phase 0：保留当前生产路线，不做推倒重来

继续保留：

- Step 13 的正式生产执行路线。
- Step 14 的当前进度与下一步计划。
- SEC filing / transcript / web / graph / policy / geo / opportunity 的长期目标。

本 Step 15 是覆盖在正式路线上的 agent workflow 产品化路线。

## Phase 1：3 天内完成 workflow skeleton

目标：

不用前端，先完成完整 backend workflow skeleton。

新增文件：

```text
src/workflows/state.py
src/workflows/finrisk_workflow.py
src/workflows/steps/company_resolver.py
src/workflows/steps/filing_risk_extractor.py
src/workflows/steps/market_explorer_step.py
src/workflows/steps/evidence_normalizer.py
src/workflows/steps/risk_scorer.py
src/workflows/steps/graph_reasoner.py
src/workflows/steps/report_generator.py
src/workflows/steps/evaluator.py
src/api/main.py
src/api/workflows.py
tests/workflows/test_workflow_contract.py
```

验收标准：

```bash
uv run pytest tests/workflows -q
uv run python -m src.workflows.finrisk_workflow --ticker AAPL --demo-mode
```

输出必须包含：

- workflow trace。
- extracted risks。
- normalized evidence。
- risk scores。
- report。
- evaluation。

## Phase 2：接入现有模块

目标：

不要重写已有能力，先把现有模块包装成 workflow step。

映射关系：

```text
TickerResolver → CompanyResolverStep
FilingFetcher + SecSections → FilingRiskExtractorStep
MarketExplorer + SearchRouter → MarketExplorerStep
GraphWriter / GraphQueries → GraphReasonerStep
ReportAgent → ReportGeneratorStep
```

验收标准：

- demo mode 可以完全离线运行。
- real filing mode 可以用 `AAPL --no-web` 跑通。
- browser 失败不导致 workflow 整体失败。

## Phase 3：加入 evaluation / guardrails

目标：

把 agent workflow 从“能跑”推进到“可评估、可解释、可审核”。

新增：

```text
eval/golden_cases.json
eval/run_eval.py
tests/workflows/test_guardrails.py
```

重点测试：

- schema valid。
- each risk has evidence。
- severity range valid。
- source URL exists。
- no financial advice。
- report has limitations section。
- report has evidence vs inference section。

验收标准：

```bash
uv run pytest tests/workflows -q
uv run python eval/run_eval.py
```

## Phase 4：做最小 Web UI

目标：

形成可展示的 Agent Workflow Demo。

页面：

- Workflow Launcher。
- Agent Timeline。
- Risk Report。
- Evidence Graph。

要求：

- 前端可以使用 cached run。
- timeline 实时或轮询更新。
- graph 可以先用 mock / workflow output 渲染。
- 不把 UI 做成聊天窗口。

验收标准：

```text
输入 AAPL → Run Workflow → Timeline 完成 → Report 显示 → Graph 显示 → Evaluation 显示 pass/needs_review
```

## Phase 5：真实数据增强

目标：

把 demo 从 cached/offline 升级到真实数据闭环。

执行顺序：

1. SEC filing real mode。
2. web search real mode。
3. transcript real mode。
4. Neo4j real graph mode。

要求：

- 每个 real mode 都有 cached fallback。
- 每个外部 provider 都有 timeout、retry、rate limit。
- integration test 默认跳过，通过环境变量开启。

## Phase 6：README、Demo Script 和部署

目标：

让项目可以被别人理解、复现和展示。

README 必须包含：

- What problem it solves。
- Architecture。
- Agent workflow。
- Structured outputs。
- Guardrails。
- Evaluation。
- How to run locally。
- How to switch LLM providers。
- Screenshots。

新增文档：

```text
docs/agent-workflow.md
docs/evaluation.md
docs/demo-script.md
docs/deployment.md
```

运行方式：

```bash
docker compose up
uvicorn src.api.main:app --reload
```

后续可选：

- Cloud Run。
- Render / Fly.io。
- Hugging Face Spaces demo。

## Demo MVP 定义

第一版 MVP 不需要完整金融生产系统，只需要一个稳定端到端案例。

建议案例：

```text
Company: Apple
Ticker: AAPL
Filing: sample Item 1A text or cached SEC filing
Browser/Search: cached CNBC / Reuters / company IR / SEC evidence
Graph: mock supplier relation or local Neo4j fixture
Report: risk intelligence brief
Eval: 5 golden cases
Frontend: one dashboard with 4 views
```

MVP 要求：

- 5 分钟内可完整演示。
- 不依赖复杂外部数据。
- browser exploration 失败时自动 fallback。
- LLM 不可用时可使用 cached structured output。
- 报告明确区分 evidence、inference、hypothesis。

## 与正式项目路线的关系

Step 13 / Step 14 关注正式项目生产能力：

- 真实 SEC filing。
- 电话会议。
- 网页搜索。
- Neo4j 图谱。
- 政策和地缘政治风险。
- 投资机会发现。
- evaluation / backtest。

Step 15 关注展示和工程组织：

- 显式 workflow。
- 前端 dashboard。
- guardrails。
- evaluation。
- provider mode。
- cached demo。
- API 化和部署。

两者不是冲突关系。建议执行策略：

```text
先用 Step 15 做出可演示 Agent Workflow；
再按 Step 13 / Step 14 不断把真实数据和生产能力替换进去。
```

## 两周执行计划

### 第 1-3 天：Workflow skeleton

- 新增 workflow state。
- 新增 8 个 workflow step。
- 新增 CLI demo mode。
- 新增 workflow contract tests。

详细执行规格见：

```text
docs/specs/01-workflow-state-and-schemas.md
docs/specs/02-workflow-steps-and-orchestration.md
```

### 第 4-5 天：接入现有模块

- 接入 ticker resolver。
- 接入 filing fetcher / section parser。
- 接入 report agent。
- 接入 graph fixture。

### 第 6-7 天：Guardrails 和 eval

- 新增 workflow evaluation schema。
- 新增 guardrail tests。
- 新增 golden cases。

详细执行规格见：

```text
docs/specs/04-evaluation-guardrails-and-golden-cases.md
```

### 第 8-10 天：FastAPI 和前端

- 新增 workflow API。
- 新增 dashboard。
- 实现 launcher、timeline、report、graph。

详细执行规格见：

```text
docs/specs/03-api-runtime-and-run-storage.md
docs/specs/05-frontend-dashboard-spec.md
```

### 第 11-12 天：Provider mode 和 cached fallback

- 增加 `LLM_PROVIDER` 配置。
- 增加 demo cached run。
- 增加 search/browser fallback。

### 第 13-14 天：README 和演示 polish

- 更新 README。
- 写 demo script。
- 截图。
- 跑完整演示。

详细集成验收规格见：

```text
docs/specs/06-demo-integration-and-acceptance.md
```

## 下一步优先级

建议立即执行：

1. 保持当前 Step 14 中的质量收口任务。
2. 修复高优先级 ruff 问题。
3. push 当前本地提交。
4. 开始 Phase 1 workflow skeleton。

不要立即做：

- 大规模目录迁移。
- 引入 LangGraph。
- 做完整生产 UI。
- 一开始就依赖真实 browser exploration。
- 一开始就依赖大型本地 GPU 模型。

## 完成定义

当以下流程稳定运行时，本阶段完成：

```bash
uv run python -m src.workflows.finrisk_workflow \
  --ticker AAPL \
  --analysis-goal "Identify macro, policy and supply-chain risks that changed recently." \
  --demo-mode
```

并且 Web UI 可以完成：

```text
Launch Workflow
→ Agent Timeline
→ Risk Report
→ Evidence Graph
→ Evaluation Result
```

最终输出必须满足：

- 每个 top risk 有 evidence。
- severity 在 1-5。
- report 无直接买卖建议。
- report 区分 evidence / inference / hypothesis。
- workflow trace 可查看。
- cached mode 可离线演示。
- API mode 和 local-LLM mode 都有配置入口。
