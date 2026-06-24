# Step 15 Combined Spec - FinRisk Agent Studio

## 目标

本文件把 `docs/specs/v15-finrisk-agent-studio/00-06` 中第 15 版 FinRisk Agent Studio 规格整理为单文件版本，方便后续编程助手一次性阅读完整上下文。

第 15 版目标：

> 将 FinText-LLM 从金融文本分析工具库升级为 FinRisk Agent Studio：一个可运行、可解释、可评估、可部署的 Agent Workflow Demo。

第 15 版强调：

- Pydantic-first custom workflow。
- cached demo mode。
- 明确的 workflow trace。
- FastAPI workflow runtime。
- 前端 dashboard。
- evidence-backed report。
- graph-based reasoning。
- evaluation / guardrails。
- local LLM 与 API provider 双模式。

第 16 版在此基础上继续升级：

- Evaluation / Guardrails 从最后 step 升级为横跨每一步的 Quality Layer。
- Graph Reasoning 从普通 step 升级为路径检索、路径排序、证据绑定、LLM/模板解释和路径校验子系统。

第 16 版详细规格见：

```text
docs/implementation-plan/16-quality-layer-and-graph-reasoning-roadmap.md
docs/specs/v16-quality-graph/
```

## 推荐执行顺序

第 15 版原始拆分规格：

```text
docs/specs/v15-finrisk-agent-studio/00-finrisk-agent-studio-spec-index.md
docs/specs/v15-finrisk-agent-studio/01-workflow-state-and-schemas.md
docs/specs/v15-finrisk-agent-studio/02-workflow-steps-and-orchestration.md
docs/specs/v15-finrisk-agent-studio/03-api-runtime-and-run-storage.md
docs/specs/v15-finrisk-agent-studio/04-evaluation-guardrails-and-golden-cases.md
docs/specs/v15-finrisk-agent-studio/05-frontend-dashboard-spec.md
docs/specs/v15-finrisk-agent-studio/06-demo-integration-and-acceptance.md
```

建议实现顺序：

1. Workflow state 与 schemas。
2. Workflow steps 与 orchestration。
3. API runtime 与 run storage。
4. Evaluation、guardrails 与 golden cases。
5. Frontend dashboard。
6. Demo integration 与最终验收。

## 全局原则

- 不推倒重来，优先复用现有 `src/` 模块。
- 第一阶段不做大规模目录迁移。
- 第一阶段不引入 LangGraph 等重框架。
- 所有 workflow step 必须有 Pydantic input/output。
- 所有最终 claim 必须绑定 evidence。
- 所有 LLM 输出必须可以被 schema 校验。
- demo mode 必须支持离线 cached fallback。
- browser、LLM、web search、Neo4j 失败不能导致 demo 完全不可演示。
- 先完成稳定可展示 workflow，再逐步替换为真实 SEC、transcript、web、Neo4j 数据。

## Spec 01：Workflow State 与 Schemas

### 新增文件

```text
src/workflows/__init__.py
src/workflows/state.py
src/schemas/finrisk.py
tests/workflows/test_workflow_schemas.py
```

### 核心 schema

必须定义：

- `FinRiskRequest`
- `CompanyProfile`
- `ExtractedRisk`
- `MarketEvidence`
- `NormalizedEvidence`
- `RiskScore`
- `GraphInsight`
- `RiskReport`
- `WorkflowTraceEvent`
- `WorkflowEvaluation`
- `FinRiskWorkflowState`

### 关键要求

- `ticker` 自动转大写。
- `analysis_goal` 不能为空。
- `severity` 必须在 1-5。
- `confidence` 必须在 0-1。
- datetime 必须 timezone-aware。
- report 必须包含 `limitations` 和 `evidence_vs_inference`。
- workflow state 必须可 JSON serialize / deserialize。

### 验收命令

```bash
uv run pytest tests/workflows/test_workflow_schemas.py -q
uv run pytest -q
```

## Spec 02：Workflow Steps 与 Orchestration

### 新增文件

```text
src/workflows/finrisk_workflow.py
src/workflows/steps/__init__.py
src/workflows/steps/company_resolver.py
src/workflows/steps/filing_risk_extractor.py
src/workflows/steps/market_explorer_step.py
src/workflows/steps/evidence_normalizer.py
src/workflows/steps/risk_scorer.py
src/workflows/steps/graph_reasoner.py
src/workflows/steps/report_generator.py
src/workflows/steps/evaluator.py
tests/workflows/test_workflow_contract.py
tests/fixtures/finrisk/aapl_demo_workflow.json
```

### Workflow steps

执行顺序：

```text
Company Resolver
→ Filing Risk Extractor
→ Market Explorer
→ Evidence Normalizer
→ Risk Scorer
→ Graph Reasoner
→ Report Generator
→ Evaluation
```

第 16 版会把 Evaluation 改成横向 Quality Layer，但第 15 版仍按最后 step 描述。

### CLI

必须支持：

```bash
uv run python -m src.workflows.finrisk_workflow \
  --ticker AAPL \
  --analysis-goal "Identify macro, policy and supply-chain risks that changed recently." \
  --demo-mode
```

### Step 要求

- Company Resolver 复用 `src/data/ticker_resolver.py`。
- Filing Risk Extractor demo mode 至少输出 3 条风险。
- Market Explorer 围绕 filing risks 定向探索，不做泛泛新闻搜索。
- Evidence Normalizer 统一 filing、web、transcript、graph evidence。
- Risk Scorer 使用 deterministic formula，不让 LLM 直接打分。
- Graph Reasoner demo mode 使用 fixture graph，Neo4j 不可用时 fallback。
- Report Generator 输出 required sections。
- Evaluator 根据结果设置 final status。

### 验收命令

```bash
uv run pytest tests/workflows/test_workflow_contract.py -q
uv run python -m src.workflows.finrisk_workflow \
  --ticker AAPL \
  --analysis-goal "Identify macro, policy and supply-chain risks that changed recently." \
  --demo-mode
```

## Spec 03：API Runtime 与 Run Storage

### 新增文件

```text
src/api/__init__.py
src/api/main.py
src/api/workflows.py
src/api/run_store.py
tests/api/test_workflow_api.py
```

### API endpoints

第一版至少支持：

```text
POST /workflows/finrisk/run
GET  /workflows/{run_id}
GET  /workflows/{run_id}/report
```

第 16 版扩展：

```text
GET /workflows/{run_id}/trace
GET /workflows/{run_id}/graph
GET /workflows/{run_id}/evaluation
GET /workflows/{run_id}/artifacts
```

### RunStore

第一版使用 `InMemoryRunStore`：

```python
class InMemoryRunStore:
    def create(self, request: FinRiskRequest) -> FinRiskWorkflowState: ...
    def get(self, run_id: str) -> FinRiskWorkflowState | None: ...
    def update(self, state: FinRiskWorkflowState) -> None: ...
    def list_recent(self, limit: int = 20) -> list[FinRiskWorkflowState]: ...
```

### 验收命令

```bash
uv run pytest tests/api/test_workflow_api.py -q
uv run pytest tests/workflows -q
```

## Spec 04：Evaluation、Guardrails 与 Golden Cases

### 新增文件

```text
src/workflows/evaluation.py
eval/golden_cases.json
eval/run_eval.py
tests/workflows/test_guardrails.py
```

第 16 版建议改为 runtime package：

```text
src/evaluation/
```

### 第 15 版 guardrails

必须检查：

- schema valid。
- 每个风险必须有 evidence。
- severity 范围 1-5。
- 禁止直接 buy/sell 投资建议。
- report 必须包含 Evidence vs Inference。
- report 必须包含 Confidence & Limitations。
- source diversity。
- graph insight supporting evidence 是否存在。

### Golden cases

至少 5 个离线 case：

- AAPL supply chain concentration。
- NVDA export control / AI chip regulation。
- MSFT cloud demand / regulatory risk。
- TSLA battery supply chain。
- XOM energy transition / policy risk。

### 验收命令

```bash
uv run pytest tests/workflows/test_guardrails.py -q
uv run python eval/run_eval.py
```

## Spec 05：Frontend Dashboard

### 推荐技术

如果项目没有前端，建议：

```text
Vite + React + TypeScript + ReactFlow
```

### 目录

```text
frontend/
├── package.json
├── index.html
├── src/
│   ├── main.tsx
│   ├── App.tsx
│   ├── api.ts
│   ├── types.ts
│   ├── components/
│   │   ├── WorkflowLauncher.tsx
│   │   ├── AgentTimeline.tsx
│   │   ├── RiskReport.tsx
│   │   ├── EvidenceGraph.tsx
│   │   └── EvaluationPanel.tsx
│   └── styles.css
```

### 第 15 版视图

```text
Workflow Launcher
Agent Timeline
Risk Report
Evidence Graph
```

第 16 版升级为：

```text
Launcher
Timeline
Risk Report
Evidence Graph
Evaluation
```

### 验收流程

```bash
uvicorn src.api.main:app --reload
cd frontend
npm install
npm run dev
```

手动验收：

```text
打开前端
输入 AAPL
开启 demo mode
Run Workflow
看到 timeline 逐步完成
看到 report
看到 evidence graph
看到 evaluation status
```

## Spec 06：Demo Integration 与最终验收

### Demo 输入

```text
Ticker: AAPL
Analysis Goal: Identify macro, policy and supply-chain risks that changed recently.
Time Horizon: 6-12 months
Mode: demo/cached
```

### Demo fixture

必须包含：

```text
tests/fixtures/finrisk/aapl_demo_workflow.json
tests/fixtures/finrisk/aapl_filing_risks.json
tests/fixtures/finrisk/aapl_market_evidence.json
tests/fixtures/finrisk/aapl_graph_insights.json
```

### Cached fallback

以下服务不可用时 demo 仍能运行：

- LLM
- browser
- web search provider
- Neo4j
- SEC network request

fallback 策略：

```text
LLM unavailable → cached structured extraction
browser unavailable → SearchRouter/cached evidence
Search unavailable → fixture market evidence
Neo4j unavailable → fixture graph insights
SEC unavailable → cached filing text / filing risks
```

### 最终验收

```bash
uv run pytest tests/workflows -q
uv run python -m src.workflows.finrisk_workflow --ticker AAPL --demo-mode
uv run pytest tests/api -q
uv run python eval/run_eval.py
uv run pytest -q
```

前端完成后：

```bash
cd frontend
npm run build
```

## 第 15 版完成定义

当一个新开发者按 README 可以在本地完成以下流程时，第 15 版完成：

```text
install dependencies
start API
start frontend
run AAPL demo
inspect timeline
read report
inspect evidence graph
see evaluation result
```

且整个流程不依赖 GPU、不依赖真实 API key、不依赖外网。
