# Chapter 3：结构校验、语义重试与显式失败

> 当前实现导读。Pydantic schema 只能证明结构合法；FinRisk 还使用 Agent output validator、
> workflow guardrail、trace/fallback 和 human review 表达不同层次的可信度。

## 本章结果

完成本章后，你应能解释：

- 字段校验、模型重试和领域质量门禁的不同职责；
- 哪些错误会成为 `ModelRetry`，哪些进入 `failed` 或 `needs_review`；
- 当前 chunk/browser/tool 路径如何表达降级；
- 为什么当前 workflow 保持顺序执行；
- 哪些空结果路径仍值得进一步类型化。

## 当前文件地图

| 文件 | 当前职责 |
| --- | --- |
| `src/schemas/finrisk.py` | 字段范围、URL、ticker 和公共 workflow schema |
| `src/ai/agents/research.py` | research output 内部 grounding 规则 |
| `src/ai/agents/structured.py` | filing/relation/planner validators 与 `ModelRetry` |
| `src/evaluation/engine.py` | 运行一组确定性 validators |
| `src/evaluation/validators/` | evidence、claim、source、financial safety 等规则 |
| `src/workflows/quality_gate.py` | step 前后校验、异常转 failed |
| `src/ai/runtime_adapter.py` | request/tool-call budget 与 tool trace |
| `src/ai/graphs/global_agent.py` | subgoal、时间、工具预算和 stop/review 状态 |
| `src/ai/graphs/parallel_policy.py` | 并行前的 read/write conflict 检查 |

## 3.1：第一层——字段和结构

Pydantic models 负责无需外部事实即可判断的规则：

- `extra="forbid"`；
- ticker 去空格并转大写；
- URL 必须使用 HTTP(S)；
- severity 为 1–5；
- confidence 为 0–1；
- browser step、quarter、graph hop 和结果数量有范围；
- stop decision 必须有 stop reason。

这层失败说明数据不符合合同，但不能证明数据真实。

## 3.2：第二层——输出内部语义

Pydantic `model_validator` 处理同一 output 内部可以判断的不变量：

- `ResearchAgentOutput` 无 evidence 时必须 `needs_review` 并说明 uncertainty；
- research source IDs 不可重复；
- `FilingRiskExtractionOutput` 空 risks 时必须 `needs_review=True`；
- confirmed supplier relation 必须有 HTTP(S) URL 和非空 quote；
- `AgentDecision` 的 stop reason 与 decision type 必须一致。

这层仍不能访问真实 evidence store，也不能确认 URL 内容、quote 来源或 graph edge 是否存在。

## 3.3：第三层——用 `ModelRetry` 修正模型决策

`build_planner_agent()` 注册 output validator，并从 `RunContext[AgentDeps]` 检查：

- 当前存在 pending subgoal 时，decision 必须选择它；
- selected scope 必须属于本次权限；
- selected tools 必须属于 `visible_tool_catalog()`。

违反规则时抛 `ModelRetry`，Pydantic AI 会把约束反馈给模型并在有界 retry 内重新生成。重试耗尽
会成为明确的 `UnexpectedModelBehavior`，测试不能把它吞成默认 decision。

`ModelRetry` 适合“模型有机会根据清晰反馈纠正”的局部输出错误，不适合 provider 断网、数据库
损坏或缺失真实证据。

## 3.4：第四层——确定性 workflow guardrails

`build_default_engine()` 当前注册七类 validator：

```text
SchemaValidator
EvidenceValidator
ClaimGroundingValidator
SourceQualityValidator
FinancialSafetyValidator
ReportStructureValidator
WorkflowValidator
```

`run_step_with_quality_gate()` 在 step 前后执行 engine。step 异常会被记录并把 state 标为 failed；
post-step findings 保存为 `StepEvaluation`，最终再汇总为 `WorkflowEvaluationV16`。

critical steps 出现 blocker 会终止主工作流；market/graph 等非关键能力允许明确降级并继续。这是
产品可用性策略，不是模型重试。

## 3.5：失败、降级和空结果

当前失败合同分布在多个层：

| 场景 | 当前表达 |
| --- | --- |
| tool backend 异常或权限拒绝 | failed `ToolResultEnvelope` + `ToolExecutionEvent` |
| subgoal runtime 异常 | subgoal failed + fallback event + stop reason |
| subgoal 没有工具证据 | `needs_review` + review item |
| browser summary 失败 | 前 200 字符 fallback |
| browser exploration 失败 | `None`，由调用方降级 |
| generic extraction client 异常 | 空 `ExtractionResult` + warning |
| filing live/provider 不可用 | keyword/cached/fixture fallback，并记录 validation/event |

空对象不能单独解释；必须同时读取 warning、fallback、component status 或 review state。

当前尚未定义统一的 `BatchSuccess | BatchFailure`，因此不能宣称所有 provider/output/domain failure
已经拥有同一种 typed error contract。

## 3.6：预算也是校验边界

`AgentBudget` 包含 subgoal、tool round、tool call、fetch page、wall-clock 和结果字符预算。
Pydantic AI 当前直接执行 request/tool-call limits；Global Agent Graph 再执行 subgoal、总时间和
总工具调用限制；browser 用 `max_steps` 约束 request/tool calls。

达到预算是可识别的停止原因，不应伪装成 provider failure。

## 3.7：为什么当前没有直接并行 chunk/workflow

`PydanticAIFilingExtractionClient.extract_risks_chunked()` 当前逐 chunk 顺序调用。FinRisk 和
Supply Chain Graph 也保持固定顺序。

`validate_parallel_group()` 会拒绝：

- write-after-write；
- write-after-read；
- read-after-write。

例如 market step 读取 filing risks，两者还共享写入 llm log，因此不能直接 fan out。若未来增加
chunk 并发，需要同时定义 concurrency limit、稳定输出排序、独立 usage 归集、部分失败和
branch-local trace buffer。

## 3.8：练习与验收

```bash
uv run python -m pytest -q \
  tests/ai/test_research_agent.py \
  tests/ai/test_structured_agents.py \
  tests/ai/test_toolsets.py \
  tests/ai/graphs/test_parallel_policy.py \
  tests/evaluation/test_guardrail_engine.py \
  tests/evaluation/test_quality_layer_runtime.py
```

推荐练习：分别制造 schema error、planner unauthorized scope、tool permission denial、step
exception 和 no-evidence subgoal，记录它们最终进入的异常或状态。

- [ ] schema error 与业务 grounding failure 没有混为一类。
- [ ] `ModelRetry` 只用于可由模型纠正的输出。
- [ ] fallback 留下可见 metadata。
- [ ] budget exhaustion 有独立 stop reason。
- [ ] 并行前先证明 state access 无冲突。
- [ ] 能指出当前空结果失败合同的不足。

下一章把这些边界放进完整的程序化工作流和 Pydantic Graph。
