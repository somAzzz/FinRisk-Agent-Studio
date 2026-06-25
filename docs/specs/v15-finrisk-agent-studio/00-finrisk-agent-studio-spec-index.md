# FinRisk Agent Studio Specs - 索引

## 目标

本目录把 `docs/implementation-plan/15-finrisk-agent-studio-workflow-roadmap.md` 拆成可直接交给编程助手执行的详细规格。

总目标：

> 将 FinText-LLM 从金融文本分析工具库升级为 FinRisk Agent Studio：一个可运行、可解释、可评估、可部署的 Agent Workflow Demo。

## 推荐执行顺序

单文件合并版：

```text
15-finrisk-agent-studio-combined-spec.md
```

拆分版：

1. `01-workflow-state-and-schemas.md`
2. `02-workflow-steps-and-orchestration.md`
3. `03-api-runtime-and-run-storage.md`
4. `04-evaluation-guardrails-and-golden-cases.md`
5. `05-frontend-dashboard-spec.md`
6. `06-demo-integration-and-acceptance.md`

第 16 版最新升级规格：

```text
docs/specs/v16-quality-graph/00-index.md
```

V16 将 Evaluation/Guardrails 从最终验收项升级为横跨每个 workflow step 的 Quality Layer，并将 Graph Reasoning 拆成图上下文构建、路径检索、路径排序、证据绑定、解释和路径校验子系统。后续实现应优先参考 V16，再回看本目录 Step 15 规格。

## 开发原则

- 不推倒重来，优先复用现有 `src/` 模块。
- 第一阶段不做大规模目录迁移。
- 第一阶段不引入 LangGraph 等重框架。
- 所有 workflow step 必须有 Pydantic input/output。
- 所有最终 claim 必须绑定 evidence。
- 所有 LLM 输出必须可以被 schema 校验。
- demo mode 必须支持离线 cached fallback。
- browser、LLM、web search、Neo4j 失败不能导致 demo 完全不可演示。
- 先完成稳定可展示 workflow，再逐步替换为真实 SEC、transcript、web、Neo4j 数据。

## 阶段性完成定义

当以下命令稳定运行时，后端 workflow 阶段完成：

```bash
uv run python -m src.workflows.finrisk_workflow \
  --ticker AAPL \
  --analysis-goal "Identify macro, policy and supply-chain risks that changed recently." \
  --demo-mode
```

输出必须包含：

- workflow trace
- company profile
- extracted risks
- normalized evidence
- risk scores
- graph insights
- report
- evaluation result

当 Web UI 可以完成以下流程时，demo 阶段完成：

```text
Launch Workflow
→ Agent Timeline
→ Risk Report
→ Evidence Graph
→ Evaluation Result
```

## 全局验收命令

每完成一个 spec 后至少运行：

```bash
uv run pytest -q
```

workflow 相关实现完成后运行：

```bash
uv run pytest tests/workflows -q
```

API 完成后运行：

```bash
uv run pytest tests/api -q
```

评估模块完成后运行：

```bash
uv run python eval/run_eval.py
```

前端完成后运行项目实际 package script，例如：

```bash
npm run build
npm run test
```

如果前端技术栈尚未建立，应在 `05-frontend-dashboard-spec.md` 的实现中补齐。
