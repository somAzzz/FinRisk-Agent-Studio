# Step 17 - 当前代码审查与 V16 对齐修正计划

## 目标

本文件记录对当前完整代码实现的审查结论，并把不符合 Step 15 / Step 16 设计要求的部分转成可执行修改方案。

审查基线：

```bash
uv run pytest -q
cd frontend && npm test -- --run
cd frontend && npm run build
uv run python -m src.workflows.finrisk_workflow \
  --ticker AAPL \
  --analysis-goal "Identify macro, policy and supply-chain risks that changed recently." \
  --demo-mode
```

当前验证结果：

```text
pytest: 494 passed, 7 skipped
frontend tests: 27 passed
frontend build: passed
workflow demo: passed
```

结论：

> 当前代码已经达到 V15/V16 demo skeleton 水平，但还没有严格达到 V16 设计。核心差距是 Quality Layer 仍偏后处理，Graph payload 仍存在 V15/V16 类型错位，V16 structured report / risk score 尚未成为主路径。

## 当前符合设计的部分

当前已经完成：

- `src/workflows/` workflow skeleton。
- `src/api/` FastAPI workflow endpoints。
- `src/evaluation/` guardrail engine、validators、metrics。
- `src/graph_reasoning/` context builder、path retriever、path scorer、evidence binder、interpreter、validator。
- `src/reports/` V16 report model 和 renderer。
- `frontend/` dashboard，包括 timeline、report、graph、evaluation 相关组件。
- demo fixture。
- API / workflow / evaluation / graph reasoning / frontend 测试。

## 主要不符合项

## P0：Quality Layer 还没有成为主 workflow 的横向 gate

### 现状

主 workflow 仍直接顺序执行 V15 steps：

```text
src/workflows/finrisk_workflow.py
```

逻辑：

```python
for step in steps:
    state = await step(state)
```

V16 的 `src/workflows/v16_runner.py` 目前是：

```text
先跑完 V15 workflow
再根据 trace 做后置 evaluation
```

这不符合 Step 16 的设计：

```text
Pre-step validation
→ Step execution
→ Post-step validation
→ State update
→ Optional gate / fallback
```

### 风险

- 错误会在前面 step 中传播到后面 step。
- blocker 无法及时阻断或触发 fallback。
- Evaluation tab 展示的是“事后审计”，不是“运行时质量层”。

### 修改方案

1. 在 `run_finrisk_workflow()` 中增加可选参数：

```python
quality_engine: GuardrailEngine | None = None
quality_gated: bool = False
```

2. 当 `quality_gated=True` 时，用：

```python
run_step_with_quality_gate()
```

包裹每个 step。

3. 让 `run_finrisk_workflow_v16()` 不再事后扫描 trace，而是调用：

```python
run_finrisk_workflow(..., quality_gated=True, quality_engine=engine)
```

4. blocker 处理规则：

```text
critical step blocker → state.status = failed
non-critical step blocker → fallback or needs_review
```

5. 每个 step 的 pre/post evaluation 必须写入：

```text
state.evaluations
state.guardrail_findings
state.trace
```

### 验收标准

新增或修改测试：

```text
tests/workflows/test_v16_quality_gated_orchestrator.py
```

必须覆盖：

- 每个 step 产生 StepEvaluation。
- pre-step blocker 可阻止 critical step。
- non-critical step 可 fallback。
- workflow_evaluation 来自 step evaluations。
- demo mode 仍可完整运行。

验收命令：

```bash
uv run pytest tests/workflows/test_v16_quality_gated_orchestrator.py -q
uv run pytest tests/evaluation tests/workflows -q
```

## P0：Graph API 返回 V15/V16 insight 类型错位

### 现状

`GraphReasonerStep` 调用 V16 subsystem 后，只保存了：

```text
state.graph_paths
state.guardrail_findings
```

但没有保存：

```text
payload.insights
payload.nodes
payload.edges
```

`GET /workflows/{run_id}/graph` 返回：

```python
"insights": [i.model_dump(mode="json") for i in state.graph_insights]
```

这里的 `state.graph_insights` 是 V15 `GraphInsight`，不是 V16 `GraphInsightV16`。

### 风险

- 前端 `GraphInsightV16` 类型与后端返回不一致。
- `risk_path_ids`、`affected_entities`、`research_theme` 等字段缺失。
- graph insight validator 结果无法和 API payload 对齐。

### 修改方案

1. 新增 state 字段：

```python
graph_payload: EvidenceGraphPayload | None = None
graph_insights_v16: list[GraphInsightV16] = []
```

如担心 import cycle，可放入 `src/schemas/finrisk_v16.py`。

2. 在 `GraphReasonerStep` 中保存完整 payload：

```python
payload = self._v16.run(state)
state.graph_payload = payload
state.graph_paths = payload.paths
state.graph_insights_v16 = payload.insights
```

3. `/graph` endpoint 直接返回：

```python
state.graph_payload.model_dump(mode="json")
```

4. 保留 `state.graph_insights` 作为 V15 report backward compatibility。

### 验收标准

增强：

```text
tests/api/test_quality_graph_api.py
tests/graph_reasoning/test_graph_reasoner_step.py
```

必须断言：

- `/graph.insights[0]` 包含 `risk_path_ids`。
- insight 引用的 path_id 存在于 payload.paths。
- insight evidence_ids 存在于 normalized evidence。
- guardrail findings 可关联 graph_path。

## P1：V16 schema 仍用 Any/list 承载，Pydantic-first 不彻底

### 现状

`FinRiskWorkflowState` 中 V16 字段为：

```python
claims: list
graph_context: Any | None
graph_paths: list
evaluations: list
workflow_evaluation: Any | None
guardrail_findings: list
fallback_events: list
```

### 风险

- schema contract 无法在 state 层保证。
- API 和 frontend 类型可能漂移。
- 测试只能检查字段存在，难以检查结构正确。

### 修改方案

新增：

```text
src/schemas/finrisk_v16.py
```

集中定义或 re-export：

- `Claim`
- `StepEvaluation`
- `WorkflowEvaluationV16`
- `FallbackEvent`
- `GraphQueryContext`
- `CandidateGraphPath`
- `GraphInsightV16`
- `EvidenceGraphPayload`

然后将 `FinRiskWorkflowState` 字段改成强类型。

如存在循环引用，优先通过 schema 文件拆分解决，而不是继续使用 `Any`。

### 验收标准

新增：

```text
tests/schemas/test_finrisk_v16_state.py
```

覆盖：

- state 可 JSON round-trip。
- graph payload 可 JSON round-trip。
- invalid graph path schema 被 Pydantic 拦截。
- invalid StepEvaluation schema 被 Pydantic 拦截。

## P1：RiskScoreV16 / RiskReportV16 尚未成为主路径

### 现状

主 workflow 使用：

```text
src/schemas/finrisk.py::RiskScore
final_score: 0-1
```

V16 的：

```text
src/reports/models.py::RiskScoreV16
src/reports/models.py::RiskReportV16
src/reports/renderer.py
```

已经存在，但未成为主 report path。

### 风险

- 前端 score breakdown 难以和 V16 规格完全一致。
- report 仍主要是 V15 `RiskReport + markdown`。
- report guardrails 无法验证结构化 claim / evidence / limitation / disclaimer 的完整关系。

### 修改方案

1. `RiskScorerStep` 同步生成：

```text
state.risk_scores_v16
```

或将主 `RiskScore` 迁移到 V16 0-100。

2. `ReportGeneratorStep` 改为：

```text
RiskReportV16 model
→ ReportStructureValidator
→ render_risk_report_markdown()
→ legacy RiskReport adapter
```

3. API `/report` 可同时返回：

```json
{
  "report": "...legacy...",
  "report_v16": "...structured...",
  "markdown": "..."
}
```

4. 前端优先消费 `report_v16`。

### 验收标准

增强：

```text
tests/workflows/test_risk_scoring.py
tests/reports/test_report_renderer.py
tests/api/test_workflow_api.py
frontend/src/components/RiskReport.test.tsx
frontend/src/components/RiskScoreBreakdown.test.tsx
```

必须验证：

- score 为 0-100。
- score_breakdown 字段完整。
- report 有 disclaimer。
- report claims 都有 evidence ids。
- markdown 由 renderer 输出。

## P1：Graph narrative 存在过强事实/概率表达

### 现状

`src/graph_reasoning/path_interpreter.py` 模板写道：

```text
creates a {confidence_pct}% probability of supply disruption
```

### 风险

- 将 path_score 误表达为真实概率。
- 违反“research theme / hypothesis，不是投资建议或确定性预测”的设计。

### 修改方案

改为：

```text
This path suggests a plausible exposure channel with path confidence {score}.
It does not prove immediate financial impact and should be treated as a research hypothesis.
```

并确保所有 `market_opportunity` 输出使用：

```text
research_theme
```

不使用：

```text
investment_theme
```

### 验收标准

新增测试：

```text
tests/graph_reasoning/test_path_interpreter_safety.py
```

禁止输出：

- probability of
- guaranteed
- buy
- sell
- should invest

## P2：Graph retriever 尚无 Neo4j backend

### 现状

`retrieve_candidate_paths()` 当前仅使用 fixture graph 或传入 nodes/edges。

### 修改方案

新增：

```text
src/graph_reasoning/backends.py
```

定义：

```python
class GraphPathBackend(Protocol):
    def retrieve(self, context: GraphQueryContext) -> list[CandidateGraphPath]:
        ...
```

实现：

- `FixtureGraphBackend`
- `Neo4jGraphBackend`

`GraphReasoningSubsystem` 注入 backend：

```python
GraphReasoningSubsystem(backend=FixtureGraphBackend())
```

### 验收标准

新增：

```text
tests/graph_reasoning/test_backends.py
```

覆盖：

- fixture backend 离线可用。
- Neo4j backend 可 mock client。
- backend 异常转成 guardrail finding。

## P2：真实数据模式仍偏浅

### 现状

- `MarketExplorerStep` real mode 未注入 router 时返回空。
- `FilingRiskExtractorStep` live mode 主要依赖 keyword fallback。
- LLM structured extraction 尚未成为主路径。

### 修改方案

1. `MarketExplorerStep` 默认构造 `SearchRouter`，而不是只有注入时才工作。
2. `FilingRiskExtractorStep` 增加 LLM structured extractor adapter。
3. real mode 失败时明确写入 `FallbackEvent`。
4. 增加可选 integration test：

```bash
RUN_SEC_INTEGRATION=1 uv run pytest tests/data -m integration
RUN_SEARCH_INTEGRATION=1 uv run pytest tests/tools -m integration
```

## P2：测试覆盖偏存在性检查，缺少语义一致性检查

### 现状

部分测试只断言：

```text
payload has nodes/edges/paths/insights
```

没有检查：

- insight path_id 是否存在。
- evidence_id 是否存在。
- API response 是否符合 frontend V16 type。
- report claim 是否能跳转 graph。

### 修改方案

新增测试：

```text
tests/api/test_v16_payload_contract.py
tests/frontend_contract/test_graph_payload_fixture.py
```

验证：

- `/graph` payload 可被 `WorkflowGraphResponse` 对应 schema 校验。
- 每个 insight risk_path_ids 都存在。
- 每个 insight evidence_ids 都存在。
- 每个 graph finding affected_object_id 可定位。

## P3：Ruff 质量门禁未收口

### 当前结果

全仓：

```text
607 errors
```

新核心目录：

```text
src/workflows src/evaluation src/graph_reasoning src/reports src/api: 132 errors
```

### 修改方案

分阶段处理：

1. 先对新核心目录执行自动修复：

```bash
uv run ruff check src/workflows src/evaluation src/graph_reasoning src/reports src/api --fix
```

2. 手动处理：

- `RUF006 asyncio.create_task`：保存 task reference 或使用 BackgroundTasks。
- `E402`：整理 API imports。
- `F401/F841`：清理 unused import / variable。
- `RUF022`：排序 `__all__`。
- `E501`：折行。

3. 暂缓 complexity 类规则：

- `PLR0912`
- `PLR0915`
- `PLR0913`

### 验收标准

先建立局部 gate：

```bash
uv run ruff check src/workflows src/evaluation src/graph_reasoning src/reports src/api
```

通过后再扩展到：

```bash
uv run ruff check src tests
```

## 推荐执行顺序

## Phase 1：修复 V16 数据流硬伤

1. 接入 quality-gated orchestrator。
2. 修复 graph payload 类型错位。
3. 增加 graph payload contract tests。

验收：

```bash
uv run pytest tests/workflows tests/evaluation tests/graph_reasoning tests/api -q
uv run python -m src.workflows.finrisk_workflow \
  --ticker AAPL \
  --analysis-goal "Identify macro, policy and supply-chain risks that changed recently." \
  --demo-mode
```

## Phase 2：主路径迁移到 V16 schema / report

1. 强类型化 V16 state 字段。
2. 接入 RiskScoreV16。
3. 接入 RiskReportV16 和 renderer。
4. 前端优先消费 V16 report。

验收：

```bash
uv run pytest tests/reports tests/workflows tests/api -q
cd frontend && npm test -- --run
cd frontend && npm run build
```

## Phase 3：真实数据与 graph backend

1. 增加 `GraphPathBackend`。
2. 增加 `Neo4jGraphBackend` mock 测试。
3. `MarketExplorerStep` 默认接入 SearchRouter。
4. `FilingRiskExtractorStep` 接入 LLM structured extraction adapter。

## Phase 4：质量门禁收口

1. 新核心目录 ruff 归零。
2. 全仓 ruff 分阶段治理。
3. CI gate 中加入：

```bash
uv run pytest -q
uv run ruff check src/workflows src/evaluation src/graph_reasoning src/reports src/api
cd frontend && npm run build
```

## 当前完成定义

完成本修正计划后，应满足：

- 主 workflow 使用 runtime Quality Layer。
- 每个 step 有 pre/post StepEvaluation。
- blocker 能阻断或触发 fallback。
- `/graph` 返回完整 V16 EvidenceGraphPayload。
- V16 insight 引用真实 path_id 和 evidence_id。
- 主 report 使用 RiskReportV16。
- score 使用 0-100 且有 breakdown。
- graph narrative 不使用真实概率或投资建议措辞。
- demo mode 不依赖 GPU/API key/Neo4j/外网。
- 核心测试和前端 build 通过。
- 新核心目录 ruff 通过。

