# V16 Specs - Quality Layer 与 Graph Reasoning

## 目标

本目录细化 `docs/implementation-plan/16-quality-layer-and-graph-reasoning-roadmap.md`。

第 16 版目标：

> 把 Evaluation/Guardrails 从最终验收项升级为横跨每一步的 Quality Layer，并把 Graph Reasoning 从单一 step 升级为路径检索、排序、证据绑定、LLM 解释和图路径校验的完整子系统。

## 执行顺序

1. `01-quality-layer-runtime.md`
2. `02-claim-grounding-and-source-quality.md`
3. `03-graph-reasoning-subsystem.md`
4. `04-structured-report-and-risk-scoring.md`
5. `05-api-and-frontend-quality-graph.md`
6. `06-v16-demo-acceptance.md`

## 与旧 specs 的关系

旧 specs 仍然有效：

```text
docs/specs/v15-finrisk-agent-studio/01-workflow-state-and-schemas.md
docs/specs/v15-finrisk-agent-studio/02-workflow-steps-and-orchestration.md
docs/specs/v15-finrisk-agent-studio/03-api-runtime-and-run-storage.md
docs/specs/v15-finrisk-agent-studio/04-evaluation-guardrails-and-golden-cases.md
docs/specs/v15-finrisk-agent-studio/05-frontend-dashboard-spec.md
docs/specs/v15-finrisk-agent-studio/06-demo-integration-and-acceptance.md
```

但 V16 对以下内容做了升级：

- `WorkflowEvaluation` 从扁平结果升级为 `StepEvaluation + GuardrailFinding + overall metrics`。
- `Evaluation` 从最后 step 改为每步 pre/post validation。
- `GraphInsight` 必须来自真实 candidate path。
- `RiskReport` 必须先结构化，再渲染 markdown。
- 前端增加 Evaluation tab。

## 全局工程要求

- 不大规模搬迁目录。
- 不引入 LangGraph。
- 不要求第一版连接真实 Neo4j。
- 不要求第一版使用真实 LLM judge。
- demo mode 必须离线可运行。
- 每个 validator 必须可单元测试。
- graph path 和 claim grounding 的失败必须可视化。

## V16 全局验收

```bash
uv run pytest tests/workflows -q
uv run pytest tests/evaluation -q
uv run pytest tests/graph_reasoning -q
uv run python -m src.workflows.finrisk_workflow --ticker AAPL --demo-mode
```

如果相关测试目录尚未创建，实现对应 spec 时同步创建。

