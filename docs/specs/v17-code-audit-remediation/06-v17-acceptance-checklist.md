# 06 - V17 Acceptance Checklist

## 目标

定义第 17 版完成标准，确保代码审查发现的问题都被转化为可验证结果。

## Phase 1：V16 数据流硬伤

必须完成：

- `run_finrisk_workflow()` 支持 `quality_engine` 和 `quality_gated`。
- `run_finrisk_workflow_v16()` 使用 quality-gated path。
- 每个 step 产生 `StepEvaluation`。
- blocker 可阻断 critical step。
- non-critical step 可 fallback。
- `GraphReasonerStep` 保存完整 `EvidenceGraphPayload`。
- `/graph` 返回 V16 graph payload。

验收：

```bash
uv run pytest tests/workflows/test_v16_quality_gated_orchestrator.py -q
uv run pytest tests/api/test_quality_graph_api.py tests/api/test_v16_payload_contract.py -q
uv run pytest tests/graph_reasoning/test_graph_reasoner_step.py -q
```

## Phase 2：V16 schema / report 主路径

必须完成：

- `FinRiskWorkflowState` V16 字段强类型化。
- `RiskScorerStep` 生成 `RiskScoreV16`。
- `ReportGeneratorStep` 生成 `RiskReportV16`。
- markdown 由 renderer 输出。
- legacy report 兼容保留。
- 前端优先消费 `report_v16`。

验收：

```bash
uv run pytest tests/schemas/test_finrisk_v16_state.py -q
uv run pytest tests/workflows/test_risk_scoring.py tests/reports/test_report_renderer.py tests/api/test_workflow_api.py -q
cd frontend && npm test -- --run
cd frontend && npm run build
```

## Phase 3：Graph backend / real mode / safety

必须完成：

- `GraphPathBackend` protocol。
- `FixtureGraphBackend`。
- `Neo4jGraphBackend` mock 测试。
- path interpreter 移除过强概率和投资建议表达。
- `MarketExplorerStep` 默认接入 `SearchRouter`。
- `FilingRiskExtractorStep` 有 LLM structured extraction adapter 或明确 fallback。
- real mode failure 写入 fallback events。

验收：

```bash
uv run pytest tests/graph_reasoning/test_backends.py tests/graph_reasoning/test_path_interpreter_safety.py -q
uv run pytest tests/workflows/test_real_mode_fallbacks.py -q
```

## Phase 4：Ruff 与回归门禁

必须完成：

- 核心目录 ruff 通过。
- 后端核心测试通过。
- 前端测试和 build 通过。

验收：

```bash
uv run ruff check src/workflows src/evaluation src/graph_reasoning src/reports src/api
uv run pytest tests/workflows tests/evaluation tests/graph_reasoning tests/api -q
cd frontend && npm test -- --run
cd frontend && npm run build
```

## 全量验收

第 17 版完成前运行：

```bash
uv run pytest -q
uv run ruff check src/workflows src/evaluation src/graph_reasoning src/reports src/api
cd frontend && npm test -- --run
cd frontend && npm run build
uv run python -m src.workflows.finrisk_workflow \
  --ticker AAPL \
  --analysis-goal "Identify macro, policy and supply-chain risks that changed recently." \
  --demo-mode
```

## 手工验收

### Workflow

输入：

```text
AAPL
Identify macro, policy and supply-chain risks that changed recently.
demo mode
```

预期：

- workflow completed。
- timeline 每个 step 有 evaluation。
- Evaluation tab 展示 per-step findings。
- report 有 disclaimer。
- graph tab 展示 V16 paths / insights。

### Graph API

请求：

```text
GET /workflows/{run_id}/graph
```

预期：

- `nodes` 非空。
- `edges` 非空。
- `paths` 非空。
- `insights` 使用 V16 schema。
- insight 的 `risk_path_ids` 能在 paths 中找到。
- insight 的 `evidence_ids` 能在 evidence table 中找到。

### Report API

请求：

```text
GET /workflows/{run_id}/report
```

预期：

- `report_v16` 非空。
- `markdown` 非空。
- `report` legacy 字段仍存在。
- disclaimer 存在。
- 无 direct buy/sell advice。

## 完成定义

V17 完成时必须满足：

```text
Quality Layer is runtime gate, not post-hoc only.
Graph payload is V16 typed.
V16 state fields are strongly typed where practical.
RiskScoreV16 / RiskReportV16 are primary paths.
Graph narrative is hypothesis-safe.
Fixture and Neo4j graph backends have tests.
Real mode failures are explicit fallback events.
Core ruff gate passes.
Backend and frontend regression tests pass.
```

## 后续连接

V17 完成后，V18 `Product Supply Chain Explorer` 可以直接复用：

- quality-gated workflow runtime。
- graph payload contract。
- report/evidence validation。
- ruff/pytest/frontend gates。
- API/frontend contract testing 思路。
