# V16 Spec 01 - Quality Layer Runtime

## 目标

实现横跨每个 workflow step 的 Evaluation / Guardrails runtime。

核心变化：

```text
旧版：workflow 最后统一 evaluate_report
新版：每个 step 执行前后都运行 guardrails，并写入 StepEvaluation
```

## 新增目录

```text
src/evaluation/
├── __init__.py
├── engine.py
├── models.py
├── validators/
│   ├── __init__.py
│   ├── schema_validator.py
│   ├── evidence_validator.py
│   ├── financial_safety_validator.py
│   ├── graph_path_validator.py
│   ├── report_structure_validator.py
│   └── workflow_validator.py
└── metrics/
    ├── __init__.py
    ├── scoring.py
    └── source_diversity.py
```

## 核心 models

定义在：

```text
src/evaluation/models.py
```

需要包含：

```python
class GuardrailSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    BLOCKER = "blocker"


class GuardrailStatus(str, Enum):
    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"
    NEEDS_REVIEW = "needs_review"


class GuardrailFinding(BaseModel):
    finding_id: str
    step_name: str
    check_name: str
    status: GuardrailStatus
    severity: GuardrailSeverity
    message: str
    affected_object_type: Literal[
        "risk",
        "evidence",
        "claim",
        "source",
        "graph_path",
        "report_section",
        "workflow",
    ]
    affected_object_id: str | None = None
    recommendation: str | None = None


class StepEvaluation(BaseModel):
    step_name: str
    status: GuardrailStatus
    findings: list[GuardrailFinding]
    metrics: dict[str, float] = {}
    latency_ms: int | None = None


class WorkflowEvaluation(BaseModel):
    run_id: str
    final_status: GuardrailStatus
    step_evaluations: list[StepEvaluation]
    overall_metrics: dict[str, float]
    blocker_count: int
    warning_count: int
    unsupported_claims: list[str]
    human_review_required: bool
```

## GuardrailEngine

定义：

```python
class GuardrailEngine:
    def validate_pre_step(
        self,
        step_name: str,
        state: FinRiskWorkflowState,
    ) -> StepEvaluation: ...

    def validate_post_step(
        self,
        step_name: str,
        output: Any,
        state: FinRiskWorkflowState,
        validators: list[Validator],
    ) -> StepEvaluation: ...

    def summarize_workflow(
        self,
        state: FinRiskWorkflowState,
    ) -> WorkflowEvaluation: ...
```

`Validator` 协议：

```python
class Validator(Protocol):
    name: str

    def validate(
        self,
        step_name: str,
        output: Any,
        state: FinRiskWorkflowState,
    ) -> list[GuardrailFinding]: ...
```

## Workflow runtime 集成

在 `src/workflows/finrisk_workflow.py` 中增加统一 step runner：

```python
async def run_step_with_quality_gate(
    state: FinRiskWorkflowState,
    step_name: str,
    step_fn: Callable[[FinRiskWorkflowState], Awaitable[Any]],
    validators: list[Validator],
    guardrail_engine: GuardrailEngine,
) -> FinRiskWorkflowState:
    ...
```

要求：

- 记录 pre-step evaluation。
- 执行 step。
- 记录 post-step evaluation。
- 将 findings 追加到 `state.guardrail_findings`。
- 将 evaluation 追加到 `state.evaluations`。
- 有 blocker 时停止或进入 fallback。
- 所有异常转成 GuardrailFinding，不裸抛到 CLI。

## State 升级

`FinRiskWorkflowState` 需要新增：

```python
evaluations: list[StepEvaluation] = []
workflow_evaluation: WorkflowEvaluation | None = None
guardrail_findings: list[GuardrailFinding] = []
fallback_events: list[FallbackEvent] = []
artifacts: dict[str, str] = {}
```

`FallbackEvent`：

```python
class FallbackEvent(BaseModel):
    event_id: str
    step_name: str
    from_mode: str
    to_mode: str
    reason: str
    occurred_at: datetime
```

## Validator v1 清单

第一版必须实现：

- `SchemaValidator`
- `EvidenceValidator`
- `FinancialSafetyValidator`
- `ReportStructureValidator`
- `WorkflowValidator`

Graph 相关 validator 见 `03-graph-reasoning-subsystem.md`。

## 验收测试

新增：

```text
tests/evaluation/test_guardrail_engine.py
tests/evaluation/test_quality_layer_runtime.py
```

测试点：

- clean step output -> PASS。
- missing required evidence -> BLOCKER。
- financial advice phrase -> NEEDS_REVIEW。
- validator exception -> converted to finding。
- step runner writes evaluations and findings to state。
- blocker stops workflow or triggers configured fallback。

## 验收命令

```bash
uv run pytest tests/evaluation/test_guardrail_engine.py -q
uv run pytest tests/evaluation/test_quality_layer_runtime.py -q
```

