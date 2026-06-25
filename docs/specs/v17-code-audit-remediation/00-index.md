# V17 Specs - Code Audit Remediation 与 V16 对齐

## 目标

本目录细化：

```text
docs/implementation-plan/17-code-audit-remediation-plan.md
```

第 17 版目标：

> 在现有 V15/V16 demo skeleton 基础上，修正代码与设计不一致的部分，使 Quality Layer 成为运行时横向 gate，Graph payload 返回 V16 类型，V16 structured report / risk score 成为主路径，并建立可回归的测试与质量门禁。

审查基线：

```text
pytest: 494 passed, 7 skipped
frontend tests: 27 passed
frontend build: passed
workflow demo: passed
```

核心差距：

- Quality Layer 仍偏后处理。
- Graph payload 存在 V15/V16 类型错位。
- V16 state 字段类型还不够强。
- `RiskScoreV16` / `RiskReportV16` 尚未完全成为主路径。
- Graph narrative 存在过强概率表达。
- Graph retriever 缺少 Neo4j backend。
- real mode 数据接入偏浅。
- Ruff 局部质量门禁未收口。

## 执行顺序

1. `01-quality-gated-orchestrator.md`
2. `02-v16-graph-payload-contract.md`
3. `03-v16-state-report-and-score-path.md`
4. `04-graph-backend-real-data-and-safety.md`
5. `05-ruff-ci-and-regression-gates.md`
6. `06-v17-acceptance-checklist.md`

## 与 V15 / V16 的关系

V17 不是新增产品功能，而是修正和加固：

```text
V15: workflow skeleton + API + frontend demo
V16: quality layer + graph reasoning design
V17: audit remediation, code/design alignment, regression gates
```

V17 完成后，V18 产品级供应链 Sankey 功能才能更稳地复用：

- quality gate。
- graph payload contract。
- report and evidence contract。
- API/frontend type contract。

## 全局验收命令

```bash
uv run pytest tests/workflows tests/evaluation tests/graph_reasoning tests/api -q
uv run pytest tests/reports tests/schemas -q
uv run ruff check src/workflows src/evaluation src/graph_reasoning src/reports src/api
cd frontend && npm test -- --run
cd frontend && npm run build
uv run python -m src.workflows.finrisk_workflow \
  --ticker AAPL \
  --analysis-goal "Identify macro, policy and supply-chain risks that changed recently." \
  --demo-mode
```

如果相关测试目录尚未创建，实现对应 spec 时同步创建。

