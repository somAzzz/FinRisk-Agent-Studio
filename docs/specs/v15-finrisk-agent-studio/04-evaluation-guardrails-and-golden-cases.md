# Spec 04 - Evaluation、Guardrails 与 Golden Cases

## 目标

让 FinRisk Agent Studio 不只是“能生成报告”，还要能用代码检查报告是否可信、是否有证据、是否包含不合规投资建议风险。

## 范围

本 spec 负责：

- workflow evaluation function
- guardrail checks
- golden cases
- eval runner
- tests

## 新增文件

```text
src/workflows/evaluation.py
eval/golden_cases.json
eval/run_eval.py
tests/workflows/test_guardrails.py
```

## Guardrail 规则

### G1：schema valid

检查：

- workflow state 可通过 Pydantic 校验。
- report 不为空。
- evaluation 不为空。

失败等级：

- schema 无法校验：`fail`
- report 缺失：`fail`

### G2：每个风险必须有 evidence

检查：

- `ExtractedRisk.evidence_quote` 非空。
- `RiskReport.top_risks` 中每个 risk 都有对应 `NormalizedEvidence`。

失败等级：

- 任一 top risk 无 evidence：`fail`

### G3：severity 范围

检查：

- risk severity 在 1-5。
- risk score 在 0-1。

失败等级：

- 超范围：`fail`

### G4：禁止直接投资建议

检查 report markdown 和 summary 中是否出现高风险措辞：

```text
buy
sell
strong buy
guaranteed return
must invest
price will
稳赚
买入
卖出
保证收益
```

要求：

- 允许出现 “not investment advice”。
- 如果出现直接建议，`financial_advice_risk=True`。

失败等级：

- 明确买卖建议：`needs_review` 或 `fail`，第一版建议 `needs_review`。

### G5：Evidence vs Inference

检查报告必须包含：

```text
Evidence vs Inference
```

并且应至少区分：

- evidence
- inference
- hypothesis

失败等级：

- 缺失 section：`needs_review`

### G6：Limitations

检查报告必须包含：

```text
Confidence & Limitations
```

失败等级：

- 缺失 section：`needs_review`

### G7：source diversity

计算：

```text
source_diversity_score = unique_source_count / max(1, evidence_count)
```

可设上限 1。

第一版阈值：

- `< 0.2` -> `needs_review`
- `>= 0.2` -> pass

### G8：unsupported claims

第一版规则：

- 报告中 Top Risks 数量不得超过 scored risks 数量。
- GraphInsight 中的 supporting evidence id 必须存在。
- Recommended questions 不算 claim。

后续增强：

- 用 LLM critic 验证 claim 是否被 evidence 支持。

## `WorkflowEvaluation` 计算逻辑

建议：

```python
def evaluate_workflow_state(state: FinRiskWorkflowState) -> WorkflowEvaluation:
    ...
```

状态规则：

- 任一 hard fail -> `final_status="fail"`
- 无 hard fail 但存在 review issue -> `final_status="needs_review"`
- 全部通过 -> `final_status="pass"`

## Golden cases

新增 `eval/golden_cases.json`：

```json
[
  {
    "case_id": "aapl_supply_chain_demo",
    "company": "Apple",
    "ticker": "AAPL",
    "analysis_goal": "Identify macro, policy and supply-chain risks that changed recently.",
    "expected_risk_types": ["supply_chain", "policy", "geopolitical"],
    "must_have_evidence": true,
    "should_not_contain": ["buy", "sell", "guaranteed return", "稳赚", "买入", "卖出"]
  }
]
```

第一版至少 5 个 case：

- AAPL supply chain concentration
- NVDA export control / AI chip regulation
- MSFT cloud demand / regulatory risk
- TSLA battery supply chain
- XOM energy transition / policy risk

可全部使用 demo fixture，不依赖真实网络。

## Eval runner

`eval/run_eval.py` 应支持：

```bash
uv run python eval/run_eval.py
```

输出：

```text
case_id,status,evidence_coverage,financial_advice_risk,unsupported_claim_count
```

要求：

- 默认使用 demo mode。
- 返回非零 exit code 当任一 case fail。
- `needs_review` 可以返回 0 或非零，项目内明确即可。第一版建议 fail 才非零。

## Tests

新增 `tests/workflows/test_guardrails.py`：

- 无 evidence 的 risk -> fail。
- severity 超范围由 Pydantic 拦截。
- report 包含 buy/sell -> financial_advice_risk true。
- 缺少 limitations -> needs_review。
- graph insight 引用不存在 evidence -> unsupported claim。
- clean demo state -> pass 或 needs_review，但不能 fail。

## 验收命令

```bash
uv run pytest tests/workflows/test_guardrails.py -q
uv run python eval/run_eval.py
```

## 完成定义

- evaluation 是代码级模块，不只依赖 prompt。
- workflow 最终状态由 evaluation 决定。
- golden cases 可以离线运行。
- 报告质量问题能被明确标记为 fail 或 needs_review。

