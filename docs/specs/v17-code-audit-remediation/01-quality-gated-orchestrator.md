# 01 - Quality-Gated Orchestrator

## 目标

把 Quality Layer 从“workflow 结束后的审计”改成“每个 step 执行前后的运行时 gate”。

当前问题：

```text
run_finrisk_workflow()
→ sequential v15 steps
→ v16_runner post-hoc evaluation
```

目标形态：

```text
Pre-step validation
→ Step execution
→ Post-step validation
→ State update
→ Trace update
→ Optional blocker / fallback
```

## 涉及文件

```text
src/workflows/finrisk_workflow.py
src/workflows/v16_runner.py
src/workflows/quality_gate.py
src/evaluation/engine.py
src/evaluation/models.py
tests/workflows/test_v16_quality_gated_orchestrator.py
```

## 实现要求

### run_finrisk_workflow 参数

在 `run_finrisk_workflow()` 中增加：

```python
quality_engine: GuardrailEngine | None = None
quality_gated: bool = False
```

默认行为保持兼容：

```python
quality_gated=False
```

不能破坏已有 V15 tests。

### run_step_with_quality_gate

新增或完善：

```python
async def run_step_with_quality_gate(
    *,
    step: WorkflowStep,
    state: FinRiskWorkflowState,
    quality_engine: GuardrailEngine,
    critical: bool,
) -> FinRiskWorkflowState:
    ...
```

执行顺序：

1. 写入 running trace。
2. `quality_engine.validate_pre_step(step.name, state)`。
3. 如果 pre-step blocker：
   - critical step：`state.status = "failed"`，结束 workflow。
   - non-critical step：记录 fallback / needs_review，跳过或继续。
4. 执行 step。
5. `quality_engine.validate_post_step(step.name, state)`。
6. 写入 `state.evaluations`。
7. 写入 `state.guardrail_findings`。
8. 根据 blocker 处理 status。
9. 写入 completed / failed trace。

### Critical Step 策略

第一版建议：

```text
company_resolver: critical
filing_risk_extractor: critical unless demo/cached fallback exists
evidence_normalizer: critical
risk_scorer: critical
report_generator: critical

market_explorer: non-critical
graph_reasoner: non-critical
```

### v16_runner 修改

`run_finrisk_workflow_v16()` 不再先跑完再扫描 trace，而是：

```python
state = await run_finrisk_workflow(
    request,
    quality_engine=engine,
    quality_gated=True,
    ...
)
state.workflow_evaluation = engine.summarize_workflow(state)
```

## Trace 要求

每个 step 至少记录：

- step_name
- status
- started_at
- completed_at
- error
- fallback_used

如果 blocker 发生，trace 必须可见。

## 测试要求

新增：

```text
tests/workflows/test_v16_quality_gated_orchestrator.py
```

测试用例：

- `quality_gated=False` 时旧路径仍通过。
- `quality_gated=True` 时每个 step 产生 `StepEvaluation`。
- pre-step blocker 阻断 critical step。
- non-critical step blocker 触发 fallback / needs_review 而不崩溃。
- post-step blocker 写入 `guardrail_findings`。
- `run_finrisk_workflow_v16()` 使用 quality-gated path。
- demo mode 仍可完整完成。

验收命令：

```bash
uv run pytest tests/workflows/test_v16_quality_gated_orchestrator.py -q
uv run pytest tests/evaluation tests/workflows -q
```

