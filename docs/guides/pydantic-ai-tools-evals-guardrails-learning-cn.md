# Pydantic AI 工具调用、Evals 与 Guardrails 代码学习清单

本文面向希望从 FinRisk Agent Studio 当前代码库学习 Pydantic AI 工程实践的开发者。目标不是逐目录浏览，而是沿着一条真实调用链理解：模型如何获得工具、工具如何被授权和审计、结果如何成为候选证据，以及 guardrail 和 eval 如何决定结果是否可接受。

项目当前声明的依赖范围是 `pydantic-ai>=2.0.0,<3.0.0`，参见 [`pyproject.toml`](../../pyproject.toml)。阅读外部教程时要注意 API 版本差异。

## 1. 先建立三层边界

```text
Pydantic AI
  Agent、typed output、deps、tool schema、tool loop、ModelRetry、UsageLimits

项目运行时 Guardrails
  权限、scope、预算、证据状态、SSRF、人工审批、质量门禁

项目 Evals
  fixture、golden case、指标、版本比较、回归判定
```

当前项目的 eval 是自建评测 harness，不是直接使用 `pydantic_evals`。Pydantic AI 负责模型运行和结构化边界，项目代码负责金融研究的证据治理和验收语义。

## 2. Pydantic AI 基础

### 2.1 最小 Agent

- [ ] 阅读 [`src/ai/smoke.py`](../../src/ai/smoke.py)。
- [ ] 阅读 [`tests/ai/test_smoke.py`](../../tests/ai/test_smoke.py)。
- [ ] 理解 `Agent(model, output_type, deps_type, instructions, name)` 五个核心参数。
- [ ] 理解为什么最小 smoke agent 不提供工具、不访问外部系统。

具体功能：创建一个无工具、无副作用、返回 Pydantic 对象的最小 Agent。

```python
Agent(
    model,
    output_type=SmokeAgentOutput,
    deps_type=AgentDeps,
    instructions=...,
)
```

### 2.2 Typed output

- [ ] 阅读 [`src/ai/agents/research.py`](../../src/ai/agents/research.py)。
- [ ] 阅读 [`tests/ai/test_research_agent.py`](../../tests/ai/test_research_agent.py)。
- [ ] 重点理解 `ResearchEvidence`、`ResearchAgentOutput` 和 `extra="forbid"`。
- [ ] 观察 `model_validator` 如何禁止“没有证据却标记 completed”。

具体功能：让模型直接返回经过 Pydantic 校验的研究结果，而不是在业务代码中手动解析 JSON。

### 2.3 多种结构化 Agent

- [ ] 阅读 [`src/ai/agents/structured.py`](../../src/ai/agents/structured.py)。
- [ ] 阅读 [`tests/ai/test_structured_agents.py`](../../tests/ai/test_structured_agents.py)。
- [ ] 比较 `build_filing_extraction_agent()`、`build_relation_extraction_agent()` 和 `build_planner_agent()`。

具体功能：让 filing、供应链、实体抽取和 planner 使用不同的 typed output，同时共用 `AgentDeps` 和模型构造边界。

### 2.4 Typed dependencies

- [ ] 阅读 [`src/ai/deps.py`](../../src/ai/deps.py)。
- [ ] 阅读 [`tests/ai/test_deps.py`](../../tests/ai/test_deps.py)。
- [ ] 理解 `AgentSubject`、`AgentPermissions`、`AgentServices` 和 `AgentDeps` 的职责。

具体功能：通过 `deps_type=AgentDeps` 把 run ID、研究对象、权限、预算、工具 catalog、trace sink 和 message recorder 注入 Agent，避免依赖全局变量。

```text
AgentDeps
├── AgentSubject
├── AgentPermissions
├── AgentBudget
└── AgentServices
```

### 2.5 模型 Provider 与设置

- [ ] 阅读 [`src/ai/model_factory.py`](../../src/ai/model_factory.py)。
- [ ] 阅读 [`src/ai/model_settings.py`](../../src/ai/model_settings.py)。
- [ ] 阅读 [`tests/ai/test_model_factory.py`](../../tests/ai/test_model_factory.py)。
- [ ] 阅读 [`tests/ai/test_model_settings.py`](../../tests/ai/test_model_settings.py)。

具体功能：统一构造 OpenAI、DeepSeek、SGLang 和 vLLM 等模型，并集中管理 endpoint、credential、profile 和模型参数。

## 3. 工具调用

### 3.1 项目工具合同

- [ ] 阅读 [`src/tools/contracts.py`](../../src/tools/contracts.py)。
- [ ] 阅读 [`tests/tools/test_tool_contracts.py`](../../tests/tools/test_tool_contracts.py)。
- [ ] 理解 `ProjectTool` 为什么不仅是一个 callable。

具体功能：给工具增加名称、描述、参数 schema、风险级别、scope、证据类型和结果长度上限。

```python
ProjectTool(
    name=...,
    parameters=...,
    callable=...,
    risk_level="read_only",
    scopes=...,
    max_result_chars=...,
    evidence_kind=...,
)
```

### 3.2 工具注册

- [ ] 阅读 [`src/tools/catalog.py`](../../src/tools/catalog.py) 中的 `build_project_tool_catalog()`。
- [ ] 第一遍只跟踪 `web_search`、`sec_fetch_filing`、`graph_path_search` 和 `browser_explore`。
- [ ] 阅读 [`tests/tools/test_tool_catalog.py`](../../tests/tools/test_tool_catalog.py)。

具体功能：将 Web、SEC filing、transcript、financial metrics、XBRL、graph 和 browser 能力注册为统一 `ToolCatalog`。

`catalog.py` 较大，不建议第一遍从头逐行阅读。先理解一个工具如何从底层 provider 进入 catalog，再扩展到其他工具族。

### 3.3 Typed tool wrapper 与 RunContext

- [ ] 阅读 [`src/ai/toolsets.py`](../../src/ai/toolsets.py) 中的 `web_search()` 和 `sec_fetch_filing()`。
- [ ] 阅读 [`tests/ai/test_toolsets.py`](../../tests/ai/test_toolsets.py)。
- [ ] 观察 `Annotated`、`Literal` 和 `Field` 如何约束模型生成的参数。

具体功能：把普通 Python 函数包装为 Pydantic AI typed tool，让 Pydantic AI 从签名生成参数 schema，并通过 `RunContext[AgentDeps]` 取得本次运行的依赖。

```python
async def web_search(
    ctx: RunContext[AgentDeps],
    query: str,
    max_results: ResultsLimit = 5,
) -> ToolResultEnvelope:
    ...
```

### 3.4 FunctionToolset 构造

- [ ] 阅读 [`build_project_function_toolset()`](../../src/ai/toolsets.py)。
- [ ] 理解 `FunctionToolset`、`Tool` 和 `toolset.add_tool()`。
- [ ] 对照测试中的 schema 和 metadata parity 断言。

具体功能：把 `ProjectTool` 批量转换为 Pydantic AI 工具，同时保留 scope、risk level、evidence kind 和结果上限等治理 metadata。

### 3.5 动态工具可见性

- [ ] 阅读 [`AgentPermissions.allows()`](../../src/ai/deps.py)。
- [ ] 阅读 [`build_scoped_toolset()`](../../src/ai/toolsets.py)。
- [ ] 阅读 `tests/ai/test_toolsets.py` 中的 `test_scoped_toolset_hides_interactive_and_wrong_scope_tools`。

具体功能：使用 `FilteredToolset` 根据本次运行的 scope 和 interactive/write 权限，动态隐藏模型无权使用的工具。

这是第一层授权：模型看不到被拒绝的工具。

### 3.6 执行点二次鉴权

- [ ] 阅读 [`_invoke_project_tool()`](../../src/ai/toolsets.py)。
- [ ] 阅读 `tests/ai/test_toolsets.py` 中的 `test_direct_tool_call_is_denied_even_if_visibility_is_bypassed`。

具体功能：即使可见性过滤被绕过，工具真正执行前仍调用 `permissions.allows(project_tool)`。

这是第二层授权：模型能否看到工具和工具能否执行是两个独立检查。

### 3.7 统一结果 Envelope、错误和截断

- [ ] 阅读 [`ToolResultEnvelope`](../../src/ai/toolsets.py)。
- [ ] 阅读 [`ProjectTool.executable()`](../../src/tools/contracts.py)。
- [ ] 阅读 [`truncate_jsonable()`](../../src/tools/contracts.py)。

具体功能：所有工具统一返回 `tool/status/data/evidence_kind/warnings/truncated/error`。工具异常被转换为可审计的 failed envelope；大结果按照单工具限制截断。

### 3.8 Tool trace

- [ ] 阅读 `_invoke_project_tool()` 构造 `ToolExecutionEvent` 的部分。
- [ ] 阅读 [`src/schemas/tool_trace.py`](../../src/schemas/tool_trace.py)。
- [ ] 阅读 `tests/ai/test_toolsets.py` 中的 `test_typed_wrapper_preserves_envelope_and_records_event`。

具体功能：记录 tool call ID、round ID、参数、结果摘要、耗时、错误、结果字符数和截断状态。

### 3.9 执行 Agent tool loop

- [ ] 阅读 [`src/ai/runtime_adapter.py`](../../src/ai/runtime_adapter.py)。
- [ ] 阅读 [`tests/ai/test_runtime_adapter.py`](../../tests/ai/test_runtime_adapter.py)。
- [ ] 重点跟踪 `PydanticAIRuntimeAdapter.run()` 到 `_run_and_record()`。

具体功能：运行 Agent，传入 deps、message history、model settings 和 usage limits，然后从模型消息中提取 `ToolCallPart` 并转换为项目现有的 runtime result。

### 3.10 调用预算

- [ ] 阅读 [`src/ai/usage.py`](../../src/ai/usage.py)。
- [ ] 阅读 `runtime_adapter.py` 中构造 `UsageLimits` 的部分。
- [ ] 阅读 [`tests/ai/test_usage.py`](../../tests/ai/test_usage.py)。

具体功能：将项目的 `AgentBudget` 转换成 Pydantic AI 的 `request_limit` 和 `tool_calls_limit`。

### 3.11 真实 Workflow 接入

- [ ] 阅读 [`src/workflows/steps/market_explorer_step.py`](../../src/workflows/steps/market_explorer_step.py)。
- [ ] 阅读 [`tests/workflows/test_llm_market_explorer_step.py`](../../tests/workflows/test_llm_market_explorer_step.py)。
- [ ] 跟踪 `_explore_llm_primary()`、runtime 调用、tool trace 保存和确定性 fallback。

具体功能：针对 filing 中已经识别的风险调用市场研究 Agent；当 Pydantic AI runtime 不可用、异常或没有产生来源支持的证据时，退回确定性检索。

### 3.12 Browser Agent，可选进阶

- [ ] 阅读 [`src/ai/browser_client.py`](../../src/ai/browser_client.py)。
- [ ] 阅读 [`tests/ai/test_browser_client.py`](../../tests/ai/test_browser_client.py)。

具体功能：学习一个上层 `browser_explore` 工具内部如何再次使用 Pydantic AI 选择受限 browser action，并通过步数和时间预算控制循环。

## 4. Planner 与有界 Agent 循环

### 4.1 Output validator 与 ModelRetry

- [ ] 阅读 [`build_planner_agent()`](../../src/ai/agents/structured.py)。
- [ ] 重点阅读 `@agent.output_validator` 修饰的 `validate_planner_scope()`。
- [ ] 阅读 `tests/ai/test_structured_agents.py` 中的 planner unauthorized-scope 测试。

具体功能：模型输出错误 subgoal、未授权 scope 或未知工具时，通过 `ModelRetry` 要求模型重新生成合法的 `AgentDecision`。

### 4.2 Planner 上下文构造

- [ ] 阅读 [`src/ai/planner_adapter.py`](../../src/ai/planner_adapter.py)。
- [ ] 阅读 [`tests/ai/test_planner_adapter.py`](../../tests/ai/test_planner_adapter.py)。

具体功能：把用户目标、workflow kind、pending subgoal、已接受证据 ID、可用 scope 和工具交给 typed planner，并记录 usage。

### 4.3 Bounded planner/subgoal loop

- [ ] 阅读 [`src/ai/graphs/global_agent.py`](../../src/ai/graphs/global_agent.py)。
- [ ] 阅读 [`tests/agents/test_global_agent_runtime.py`](../../tests/agents/test_global_agent_runtime.py)。
- [ ] 按下面的状态转换顺序阅读。

```text
initialize
→ plan_next
→ execute_subgoal
→ evidence normalization
→ plan_next / finish
```

具体功能：控制最大 subgoal、总运行时间、工具调用数、工具失败、无证据状态和人工复核。

## 5. 证据与安全 Guardrails

### 5.1 Tool success 到 evidence candidate

- [ ] 阅读 [`src/evidence/candidates.py`](../../src/evidence/candidates.py)。
- [ ] 阅读 [`tests/evidence/test_evidence_candidate_normalizer.py`](../../tests/evidence/test_evidence_candidate_normalizer.py)。
- [ ] 重点阅读 `_rows_for_tool()`、`_candidate_rejection_reason()`、`_source_quality_score()`、`_grounding_score()` 和 `_dedupe_candidates()`。

具体功能：把工具 trace 转换为 `accepted/rejected/needs_review` 候选证据。`tool status=success` 只说明工具成功执行，不代表内容已经成为可信事实。

### 5.2 SSRF 防护

- [ ] 阅读 [`src/security/url_guard.py`](../../src/security/url_guard.py)。
- [ ] 阅读 [`src/tools/web_fetch.py`](../../src/tools/web_fetch.py)。
- [ ] 阅读 [`tests/security/test_url_guard.py`](../../tests/security/test_url_guard.py)。

具体功能：阻止危险 scheme、localhost、private IP 和其他不允许的目标，降低模型控制 URL 时的 SSRF 风险。

### 5.3 Memory 写入 Guardrails

- [ ] 阅读 [`src/evaluation/memory_guardrails.py`](../../src/evaluation/memory_guardrails.py)。
- [ ] 阅读 [`tests/evaluation/test_memory_guardrails.py`](../../tests/evaluation/test_memory_guardrails.py)。

具体功能：LLM 抽取、Web 内容和 hypothesis 不能直接成为长期 active fact；无证据的 confirmed graph edge 被拒绝。

### 5.4 Context Guardrails

- [ ] 阅读 [`src/evaluation/context_guardrails.py`](../../src/evaluation/context_guardrails.py)。
- [ ] 阅读 [`tests/evaluation/test_context_guardrails.py`](../../tests/evaluation/test_context_guardrails.py)。

具体功能：在 context pack 进入模型前检查 token budget、manifest、过期证据、hypothesis、rejected memory 和来源多样性。

### 5.5 延迟审批和 replay protection

- [ ] 阅读 [`src/ai/approvals.py`](../../src/ai/approvals.py)。
- [ ] 阅读 [`tests/ai/test_deferred_tools.py`](../../tests/ai/test_deferred_tools.py)。

具体功能：实现审批 TTL、decision token、SQLite 原子领取、过期处理和重复执行防护。

当前 catalog 没有正式的 `write_gated` 工具，因此这里主要是审批基础设施合同，不应描述为已经接入大量真实写操作。

## 6. Workflow Guardrails

### 6.1 Finding、Severity 和 Verdict

- [ ] 阅读 [`src/evaluation/models.py`](../../src/evaluation/models.py)。
- [ ] 理解 `GuardrailFinding`、`StepEvaluation` 和 `WorkflowEvaluationV16`。
- [ ] 区分 status 与 severity。

具体功能：表达 `pass/needs_review/fail`、发现严重度、受影响对象、修复建议和 workflow 汇总结果。

### 6.2 Validator 插件合同

- [ ] 阅读 [`src/evaluation/validators/base.py`](../../src/evaluation/validators/base.py)。

具体功能：让所有 validator 实现相同的 `validate(step_name, output, state)` 接口，可以被 `GuardrailEngine` 统一组合。

### 6.3 逐个阅读具体 Validator

| 检查项 | 实现文件 | 推荐测试 |
| --- | --- | --- |
| Pydantic schema 合法性 | [`schema_validator.py`](../../src/evaluation/validators/schema_validator.py) | [`test_guardrail_engine.py`](../../tests/evaluation/test_guardrail_engine.py) |
| 每个风险是否有证据 | [`evidence_validator.py`](../../src/evaluation/validators/evidence_validator.py) | [`test_guardrail_engine.py`](../../tests/evaluation/test_guardrail_engine.py) |
| Claim 是否引用真实 evidence | [`claim_grounding_validator.py`](../../src/evaluation/validators/claim_grounding_validator.py) | [`test_claim_grounding_validator.py`](../../tests/evaluation/test_claim_grounding_validator.py) |
| 来源质量和多样性 | [`source_quality_validator.py`](../../src/evaluation/validators/source_quality_validator.py) | [`test_source_quality_validator.py`](../../tests/evaluation/test_source_quality_validator.py) |
| 投资建议和过度确定措辞 | [`financial_safety_validator.py`](../../src/evaluation/validators/financial_safety_validator.py) | [`test_guardrail_engine.py`](../../tests/evaluation/test_guardrail_engine.py) |
| 报告必要章节 | [`report_structure_validator.py`](../../src/evaluation/validators/report_structure_validator.py) | [`test_guardrail_engine.py`](../../tests/evaluation/test_guardrail_engine.py) |
| Workflow 基本不变量 | [`workflow_validator.py`](../../src/evaluation/validators/workflow_validator.py) | [`test_guardrail_engine.py`](../../tests/evaluation/test_guardrail_engine.py) |

### 6.4 GuardrailEngine

- [ ] 阅读 [`src/evaluation/engine.py`](../../src/evaluation/engine.py)。
- [ ] 阅读 [`tests/evaluation/test_guardrail_engine.py`](../../tests/evaluation/test_guardrail_engine.py)。
- [ ] 跟踪 `_safe_validate()`、`validate_pre_step()`、`validate_post_step()` 和 `summarize_workflow()`。

具体功能：组合 validator，将 validator 异常转换为 blocker，生成每一步的 evaluation，并汇总 workflow verdict 和总体指标。

### 6.5 Guardrail 嵌入 Workflow step

- [ ] 阅读 [`src/workflows/quality_gate.py`](../../src/workflows/quality_gate.py)。
- [ ] 阅读 [`tests/evaluation/test_quality_layer_runtime.py`](../../tests/evaluation/test_quality_layer_runtime.py)。

具体功能：在 step 执行前后运行验证器；捕获 step 异常；记录 blocker、latency、trace 和状态。

### 6.6 默认 Validator 集合与最终汇总

- [ ] 阅读 [`src/workflows/v16_runner.py`](../../src/workflows/v16_runner.py)。
- [ ] 阅读 [`tests/workflows/test_v16_quality_gated_orchestrator.py`](../../tests/workflows/test_v16_quality_gated_orchestrator.py)。

具体功能：组装默认 validator 集合，运行质量门禁版本的 FinRisk workflow，并设置 `state.workflow_evaluation`。

## 7. Evals

### 7.1 Workflow golden dataset

- [ ] 阅读 [`eval/golden_cases.json`](../../eval/golden_cases.json)。
- [ ] 区分输入字段、期望字段和实际进入判分的字段。

具体功能：定义离线 workflow case、ticker、研究目标和安全期望。

### 7.2 离线 Eval runner

- [ ] 阅读 [`eval/run_eval.py`](../../eval/run_eval.py)。
- [ ] 跟踪 `_load_cases()`、`_case_to_request()`、`_evidence_coverage()`、`_run_case()` 和退出码。
- [ ] 运行 `uv run python eval/run_eval.py`。

具体功能：加载 case，在 demo fixture 上运行 workflow，计算证据覆盖和安全指标，打印结果，并在出现 fail 时返回非零退出码。

### 7.3 Agent tool-trace golden eval

- [ ] 阅读 [`src/evaluation/agent_eval.py`](../../src/evaluation/agent_eval.py)。
- [ ] 阅读 [`tests/evaluation/test_agent_golden_cases.py`](../../tests/evaluation/test_agent_golden_cases.py)。
- [ ] 阅读 [`tests/fixtures/agent_golden_cases/`](../../tests/fixtures/agent_golden_cases/)。

具体功能：基于预置 tool events 评估工具族选择、候选证据纪律、stop/review 行为和安全边界。

### 7.4 禁止测试误调用真实模型

- [ ] 阅读 [`tests/conftest.py`](../../tests/conftest.py)。
- [ ] 阅读 `tests/ai/` 中使用 `TestModel` 和 `FunctionModel` 的测试。

具体功能：设置 `models.ALLOW_MODEL_REQUESTS = False`，让意外的真实 provider 请求在测试期间直接失败，同时允许可重复的测试模型运行。

### 7.5 Live acceptance

- [ ] 阅读 [`src/ai/live_acceptance.py`](../../src/ai/live_acceptance.py)。
- [ ] 阅读 [`tests/ai/test_live_acceptance.py`](../../tests/ai/test_live_acceptance.py)。
- [ ] 阅读 [`docs/guides/llm-provider-validation.md`](llm-provider-validation.md)。

具体功能：验证真实 provider 的 structured output 和 tool-call 协议是否可用。Live acceptance 用于真实集成验收，不能替代稳定、离线、可重复的回归 eval。

## 8. 最短学习路径

第一轮只读以下八个文件：

1. [`src/ai/smoke.py`](../../src/ai/smoke.py)
2. [`src/ai/agents/research.py`](../../src/ai/agents/research.py)
3. [`src/ai/deps.py`](../../src/ai/deps.py)
4. [`src/tools/contracts.py`](../../src/tools/contracts.py)
5. [`src/ai/toolsets.py`](../../src/ai/toolsets.py)
6. [`src/ai/runtime_adapter.py`](../../src/ai/runtime_adapter.py)
7. [`src/evidence/candidates.py`](../../src/evidence/candidates.py)
8. [`src/evaluation/engine.py`](../../src/evaluation/engine.py)

运行配套测试：

```bash
uv run pytest \
  tests/ai/test_smoke.py \
  tests/ai/test_research_agent.py \
  tests/ai/test_toolsets.py \
  tests/ai/test_runtime_adapter.py \
  tests/evidence/test_evidence_candidate_normalizer.py \
  tests/evaluation/test_guardrail_engine.py \
  -q
```

完成后再阅读 planner、global graph 和完整 workflow。最终应该能够独立解释下面这条链路：

```text
Agent
→ typed output
→ injected deps
→ scoped toolset
→ runtime authorization
→ tool event
→ evidence candidate
→ guardrail finding
→ step evaluation
→ workflow verdict
→ offline eval
```

## 9. 建议的动手练习

### 练习一：增加一个只读工具

1. 在 `src/tools/catalog.py` 注册工具。
2. 在 `src/ai/toolsets.py` 增加 typed wrapper。
3. 设置 scope、risk level、evidence kind 和结果上限。
4. 在 `tests/ai/test_toolsets.py` 验证 schema、可见性、执行鉴权和 trace。
5. 如果工具产生证据，在 `src/evidence/candidates.py` 增加 row adapter 和 normalizer 测试。

验收标准：模型只能在授权 scope 中看到工具；直接绕过 visibility 仍不能越权；成功和失败均产生 trace；证据不能绕过 candidate 状态。

### 练习二：增加一个 Guardrail

1. 在 `src/evaluation/validators/` 新建 validator。
2. 返回结构化 `GuardrailFinding`，明确 status、severity、object ID 和 recommendation。
3. 在 `build_default_engine()` 注册。
4. 为 pass、warning、blocker 和 validator exception 编写测试。
5. 验证最终 workflow verdict 是否按预期变化。

验收标准：validator 是确定性的；异常不会使审计信息消失；finding 能定位到具体对象；runtime 和 API 能看到聚合结果。

### 练习三：增加一个 Eval case

1. 明确要比较的行为和失败定义。
2. 准备独立输入 fixture，避免所有 case 共享同一份业务数据。
3. 先写期望结果，再运行候选系统。
4. 同时加入正样本、负样本和边界样本。
5. 确保期望字段实际参与 verdict 和退出码。

验收标准：case 可以离线复现；结果可以区分 pass、needs_review 和 fail；失败会影响 CI；评测同时报告质量和成本。

## 10. 阅读时必须留意的当前实现债务

以下代码适合用于学习审查思路，但不应原样当作最佳实践复制：

1. `EvidenceValidator` 的 report-level 分支目前把 risk ID 与 evidence ID 集合直接比较，关系检查应改为使用 evidence 的 `related_risk_ids`。
2. `GuardrailEngine._status_for()` 当前只显式聚合 `BLOCKER` 和 `WARNING`，没有正确处理 `ERROR` severity。
3. `quality_gate.py` 的 pre-step blocker 当前只记录日志，仍继续执行 step；pre/post validator 语义尚需拆分。
4. `eval/run_eval.py` 的 workflow cases 当前共享 AAPL fixture，主要证明 workflow/guardrail contract 没有回归，不代表跨公司风险识别准确率。
5. `should_not_contain` 会被计算并输出，但当前没有直接决定 runner 的退出码。
6. `_invoke_project_tool()` 将 envelope 截成 500 字符写入 `result_summary`，而 candidate normalizer 又从该摘要解析证据；审计摘要和完整 evidence payload 应进一步解耦。

学习这个项目时，既要理解已经建立的 typed tool、evidence-first 和 quality-gate 边界，也要练习识别这些边界之间仍然存在的契约缺口。
