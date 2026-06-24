# Spec 02 - Workflow Steps 与 Orchestration

## 目标

实现 FinRisk Agent Studio 的后端 workflow skeleton。第一版以可运行、可追踪、可 fallback 为目标，不追求真实数据全量接入。

## 范围

本 spec 负责：

- workflow orchestrator
- 8 个 workflow steps
- demo mode / cached mode
- CLI 入口
- workflow contract tests

不负责：

- FastAPI 持久化接口，见 `03-api-runtime-and-run-storage.md`
- 前端 UI，见 `05-frontend-dashboard-spec.md`
- 完整 evaluation，见 `04-evaluation-guardrails-and-golden-cases.md`

## 新增文件

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

## Step contract

每个 step 建议暴露一个 async 函数：

```python
async def run_step(state: FinRiskWorkflowState) -> FinRiskWorkflowState:
    ...
```

或者暴露 class：

```python
class CompanyResolverStep:
    name = "company_resolver"

    async def run(self, state: FinRiskWorkflowState) -> FinRiskWorkflowState:
        ...
```

第一版建议使用 class，方便后续注入依赖和 mock。

## Trace 规则

每个 step 必须：

- 开始时追加或更新 trace event 为 `running`。
- 成功后更新为 `completed`。
- 跳过时更新为 `skipped`。
- 失败但可 fallback 时记录 error，并继续 workflow。
- 失败且不可恢复时设置 state.status 为 `failed`。

trace event 必须包含：

- `step_name`
- `status`
- `started_at`
- `completed_at`
- `input_summary`
- `output_summary`
- `error`
- `retry_count`

## Orchestrator

`src/workflows/finrisk_workflow.py` 应提供：

```python
async def run_finrisk_workflow(request: FinRiskRequest) -> FinRiskWorkflowState:
    ...
```

执行顺序：

1. Company Resolver
2. Filing Risk Extractor
3. Market Explorer
4. Evidence Normalizer
5. Risk Scorer
6. Graph Reasoner
7. Report Generator
8. Evaluation

要求：

- 每步只读写 `FinRiskWorkflowState`。
- workflow 不直接操作 loose dict。
- demo mode 不依赖网络、LLM、browser、Neo4j。
- 非 demo mode 若某个外部服务失败，应降级为 `needs_review` 或 cached fallback，而不是直接崩溃。

## CLI 入口

支持：

```bash
uv run python -m src.workflows.finrisk_workflow \
  --ticker AAPL \
  --analysis-goal "Identify macro, policy and supply-chain risks that changed recently." \
  --demo-mode
```

CLI 输出：

- run_id
- final status
- completed steps
- top risks summary
- report markdown path 或 markdown 内容
- evaluation status

## Step 1：Company Resolver

职责：

- 复用 `src/data/ticker_resolver.py`。
- demo mode 返回 fixture company profile。
- real mode 使用 SEC ticker resolver。

最低验收：

- `AAPL` 返回 `Apple Inc.` 和 `0000320193`。
- 无法解析 ticker 时 workflow fail fast，错误明确。

## Step 2：Filing Risk Extractor

职责：

- demo mode 从 fixture 生成 3-5 条风险。
- real mode 复用 filing fetcher 和 section parser。
- LLM 不可用时使用 rule fallback 或 cached extraction。

最低验收：

- 至少输出 3 条 `ExtractedRisk`。
- 每条 risk 有 `risk_id`、`risk_type`、`severity`、`evidence_quote`。
- 没有 evidence 的 risk 不进入 state。

## Step 3：Market Explorer

职责：

- 根据 `filing_risks` 生成 targeted exploration goals。
- demo mode 从 fixture 返回 cached market evidence。
- real mode 优先使用 SearchRouter，browser exploration 作为增强。

最低验收：

- 不进行泛泛新闻搜索。
- 每条 market evidence 关联至少一个 risk，或明确标记为 general market signal。
- browser/search 失败时 workflow 继续，并记录 trace error。

## Step 4：Evidence Normalizer

职责：

- 将 filing risks 和 market evidence 转为 `NormalizedEvidence`。
- 做 ID 去重和 source URL 去重。
- 标记 evidence / inference / hypothesis 边界。

最低验收：

- 每个 top risk 至少有一个 normalized evidence。
- 同一 source URL 的重复 evidence 被合并或标记。

## Step 5：Risk Scorer

职责：

- 用 deterministic formula 计算风险分数。

建议公式：

```text
final_score =
  0.35 * normalized_base_severity
  + 0.25 * recent_signal_strength
  + 0.20 * evidence_quality
  + 0.10 * source_diversity
  + 0.10 * novelty_score
```

要求：

- `normalized_base_severity = severity / 5`
- 所有子分数限制在 0-1。
- LLM 只能解释分数，不能改分数。

最低验收：

- 每个 risk 有对应 RiskScore。
- final_score 在 0-1。
- score_reasoning 非空。

## Step 6：Graph Reasoner

职责：

- demo mode 使用 fixture graph。
- real mode 复用 Neo4j writer/query。
- 输出 second-order effects。

最低验收：

- 至少输出 1 条 GraphInsight。
- 每条 insight 有 risk_path 和 supporting evidence。
- Neo4j 不可用时可以 fallback 到 fixture graph。

## Step 7：Report Generator

职责：

- 生成 `RiskReport` 和 markdown。
- 不输出直接买卖建议。
- 区分 evidence / inference / hypothesis。

最低报告 sections：

```markdown
## Executive Summary
## Top Risks
## Recent Changes
## Evidence Table
## Second-Order Effects
## Evidence vs Inference
## Confidence & Limitations
## Recommended Next Research Questions
```

## Step 8：Evaluator

职责：

- 调用 evaluation/guardrail logic。
- 设置 `state.evaluation`。
- 根据结果设置最终 status。

规则：

- `pass` -> `state.status = "completed"`
- `needs_review` -> `state.status = "needs_review"`
- `fail` -> `state.status = "failed"`

## 测试要求

新增 `tests/workflows/test_workflow_contract.py`：

- demo workflow 可以完整运行。
- trace 包含 8 个 step。
- 每个 step 最终为 completed 或 skipped。
- top risks 非空。
- evidence 非空。
- risk scores 非空。
- report markdown 包含 required sections。
- evaluation final_status in pass/needs_review/fail。
- browser/search/Neo4j mock failure 不导致 demo workflow 崩溃。

## 验收命令

```bash
uv run pytest tests/workflows/test_workflow_contract.py -q
uv run python -m src.workflows.finrisk_workflow \
  --ticker AAPL \
  --analysis-goal "Identify macro, policy and supply-chain risks that changed recently." \
  --demo-mode
```

## 完成定义

- demo mode 端到端稳定运行。
- workflow state 可 JSON 序列化。
- trace 可用于前端 timeline 展示。
- 不依赖真实外部服务。

