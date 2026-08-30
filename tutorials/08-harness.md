# Chapter 8：用实验选择 Harness Capabilities

## 本章结果

本章不是“把 Core 换成 Harness”。Harness 通过 Pydantic AI 的 capabilities/hooks 扩展
同一个 Agent。你将以 Chapter 7 的 Core/Pydantic Graph 为 baseline，逐项测试
Planning、SubAgents、ToolOutputLimits，以及可选的 DynamicWorkflow，最后只接入有明确
收益且不破坏领域边界的 capability。

截至 2026-08-31，本仓库锁定 `pydantic-ai-slim 2.33.0`；本章使用
`pydantic-ai-harness 0.27.0`。Harness 仍为 `0.x`，minor release 可能破坏 API。

前置条件：Chapter 7 已完成 cutover，source/import gate 能证明旧 runtime 已删除，且
Core/Pydantic Graph 全量回归通过。

## 文件变更总览

### 修改依赖

| 文件 | 修改内容 | 意义 |
| --- | --- | --- |
| `pyproject.toml` | 在独立 dependency group 中精确加入 `pydantic-ai-harness==0.27.0` | 避免实验依赖无意成为所有部署的隐式依赖 |
| `uv.lock` | 提交解析后的完整 lock | 固定 capability API 与传递依赖 |

建议命令：

```bash
uv add --group harness "pydantic-ai-harness==0.27.0"
uv lock --check
```

若你选择不同版本，必须在本章文档顶部记录版本、原因和官方 release notes 链接，并按
实际签名更新测试，不能复制旧示例后用 `Any` 绕过类型问题。

### 新建文件

| 文件 | 必须实现的职责 | 可能替代的职责 |
| --- | --- | --- |
| `src/ai/harness/__init__.py` | 只导出项目采用的 capability profile | 避免业务模块直接拼 capability 列表 |
| `src/ai/harness/config.py` | typed `HarnessProfile`，表达 enabled capability 与 limits | 替代散落 bool flags；不是双 runtime 开关 |
| `src/ai/harness/capabilities.py` | 根据 profile 构造 Planning/SubAgents/ToolOutputLimits | 替代重复的 Agent capability 组装代码 |
| `src/ai/harness/events.py` | 把 plan/delegation/spill 事件投影到项目 trace | 替代 capability 事件只留在模型上下文/日志 |
| `src/ai/harness/overflow_store.py` | 项目控制的 overflow 存储与保留策略 | 替代不可审计的静默字符串截断 |
| `src/ai/harness/orchestration.py` | Core delegation、SubAgents、DynamicWorkflow 的可比较入口 | 只替代经测量证明冗余的 delegation boilerplate |
| `scripts/pydantic_ai_harness_smoke.py` | 当前锁定版本的 import + 最小 capability smoke | 尽早发现 API/version 不匹配 |
| `scripts/compare_core_harness.py` | 同 fixtures 运行 Core 与 Harness 并输出 JSON 报告 | 替代人工观察“感觉更好” |
| `tests/fixtures/harness/cases.json` | 固定任务与 fake tool responses | 保证两种路径输入一致 |

### 新建测试

```text
tests/ai/harness/
  __init__.py
  test_config.py
  test_capabilities.py
  test_planning.py
  test_subagents.py
  test_tool_output_limits.py
  test_dynamic_workflow.py
  test_events.py
  test_orchestration_comparison.py
```

如果最终不采用 DynamicWorkflow，保留对比报告和拒绝理由，但不必把
`test_dynamic_workflow.py` 作为生产回归测试长期维护。

### 修改文件

| 文件 | 修改内容 | 限制 |
| --- | --- | --- |
| `src/ai/agents/research.py` | 允许 composition root 注入 capabilities | output/deps/toolsets 合同保持不变 |
| `src/api/agent_runs.py` 或你的 composition root | 选择已批准的 profile | 不允许用户 prompt 任意开启 capability |
| `src/agents/state.py` | 如有需要增加 plan/delegation/spill trace 类型 | plan 不得成为 evidence |

本章不删除 Pydantic Graph，也不恢复 Chapter 7 已删除的旧 runtime。

## 8.1：先建立不可变的 Core baseline

在加 Harness 前固定至少 12 个离线 case：

- 3 个简单单工具任务；
- 3 个多来源 filing/market 任务；
- 2 个可并行 specialist 任务；
- 2 个超长 tool output；
- 1 个 child failure；
- 1 个 missing evidence。

每个 case 固定 prompt、deps/permissions、fake tool responses、预算和预期领域结果。记录：

```text
status
model_requests
tool_calls and duplicate calls
input/output/total tokens
accepted evidence IDs
unsupported claims
human-review items
latency
trace event completeness
```

Core baseline 必须使用 Chapter 7 的正式 Agent 和 validators，不另写一个简化 Agent。

## 8.2：Planning 实验

当前 `Planning` 提供模型可维护的结构化 task list，并可使用内存或持久 store；它能表达
subtasks/dependencies，也会产生 plan events。它解决长任务漂移，不是业务 workflow
状态机。

先只加入 `Planning()`，验证：

- 简单任务是否产生无意义计划和额外请求；
- 三步以上任务是否减少遗漏/重复工具调用；
- 失败后 plan 是否更新；
- 同一时刻是否只保持一个 `in_progress` task；
- plan event 是否带项目 run/subgoal correlation；
- plan 是否从不进入 evidence/claim store；
- store 失败是 fail-closed 还是有明确的项目 fallback policy。

只有开放式长任务从中获益时才采用。固定 FinRisk 主 workflow 的步骤、quality gate 和
checkpoint 继续由 Pydantic Graph 管理；不要用模型计划替换它们。

若采用持久 plan store，namespace/session 必须由服务端 deps 解析，不能由模型提供。

## 8.3：SubAgents 实验

把 Chapter 7 的 specialists 包装成 child Agents，但不要改变它们的 typed output 和
tool isolation。

必须验证：

- parent 给 child 的 task 是自包含文本，不引用模糊的“上面的内容”；
- child 具有独立 message context；
- deps 中 principal/tenant/permissions 的继承规则明确；
- child 的 request/tool/token/deadline 上限可执行；
- parent 能区分 completed、needs_review、timeout、failed；
- child usage 能归集到整个 run；
- child output 仍经过 evidence normalization 和 quality gate；
- parent 无法借 delegation 获得自己没有的 tool permission。

比较 Chapter 7 的 Core delegation 与 Harness SubAgents：样板代码、模型轮次、上下文占用、
usage 归集和失败隔离。SubAgents 只在这些维度有实际优势时替换 delegation tools。

## 8.4：ToolOutputLimits 实验

当前 capability 可按阈值 passthrough、truncate、summarize 或 spill，并支持 fallback chain。
默认行为可能随版本变化，所以在 `capabilities.py` 中显式配置阈值、action、store 与
serializer，不依赖隐式默认。

用 filing tool 返回三类超大数据：长文本、结构化 records、binary。测试：

- 模型上下文中的返回有界；
- structured output spill 后仍可按记录/行分页读取；
- 原始 payload 写入项目控制的 store，handle 不暴露绝对路径；
- store 写失败执行明确 fallback，不静默丢失；
- spill/truncate/summarize 进入 trace；
- retention/cleanup policy 可执行；
- citation 不能引用模型从未看见且系统无法重新读取的片段；
- summarization 产生的额外 model usage 被计入预算。

Chapter 6 已有领域级 `max_result_chars` 时，必须指定唯一主责：

- 领域层负责 backend payload 的业务上限与 evidence retention；
- Harness 负责进入模型 context 的最后一道通用限制。

不要在两层各自静默截断，否则无法解释内容在哪里丢失。原始证据与模型上下文副本是两个
不同对象，分别有 retention 与 size policy。

## 8.5：可选 DynamicWorkflow 实验

DynamicWorkflow 让模型在一次受控脚本调用中组织 sub-agent fan-out/chaining，可能减少
coordinator 的模型往返和中间上下文污染，也扩大了模型控制的编排范围。

只对“多个独立研究子问题并行，最后汇总”的 case 测试。必须限制：

- 可调用的 agent allowlist；
- `max_agent_calls` 或锁定版本提供的等价限制；
- 并发上限与 deadline；
- 输入/输出大小；
- 禁止 file/shell/network capability，除非该任务明确需要且另有 policy；
- child 输出仍是 typed result，或在进入领域层前有强校验边界。

不要把 DynamicWorkflow 用于要求严格固定顺序、可恢复 checkpoint 或关键资金/写操作的
主流程。若它只让 trace 更难解释或提高 unsupported claim rate，应拒绝采用。

## 8.6：四层预算模型

在 `HarnessProfile` 与项目 state 中分别表达：

| 层 | 示例 | 执行者 |
| --- | --- | --- |
| Core usage | requests、tool calls、tokens | Pydantic AI `UsageLimits` |
| Harness capability | child calls、summarizer requests、spill/read limits | 对应 capability |
| Domain | companies、sources、graph paths、review items | workflow/domain state |
| Wall clock/cost | deadline、provider cost ceiling | application infrastructure |

不允许多个层对同一计数各自维护不同值。整个 parent/child tree 的 usage 归集语义必须通过
锁定版本的测试确认，而不是依据旧文档猜测。

## 8.7：选择，而不是全装

`scripts/compare_core_harness.py` 输出每个 case 的 baseline 与 variant diff。最低 gate：

| 指标 | 通过条件 |
| --- | --- |
| unsupported claim rate | 不得恶化 |
| permission violations | 必须为 0 |
| deterministic score parity | 必须保持 |
| accepted evidence | 不低于 baseline，或有书面解释 |
| duplicate tool calls | 长任务应下降或至少不显著增加 |
| request/token/latency | 增量必须与质量收益匹配 |
| trace completeness | plan/child/spill 均可关联 |
| failure classification | capability failure 不得伪装成 provider/domain success |

最终在 `HarnessProfile` 只保留通过 gate 的 capability。Core baseline 用于评估和回归，
不是生产时自动 fallback 的第二套 runtime。

## 本章验收

```bash
uv run --group harness python scripts/pydantic_ai_harness_smoke.py
uv run --group harness pytest -q tests/ai/harness
uv run --group harness python scripts/compare_core_harness.py \
  --cases tests/fixtures/harness/cases.json
uv run ruff check src/ai/harness tests/ai/harness scripts/pydantic_ai_harness_smoke.py
```

- [ ] Harness 与 Pydantic AI 版本精确锁定且 smoke 通过。
- [ ] Core baseline 与每个 capability variant 使用相同 fixtures。
- [ ] Planning、SubAgents、ToolOutputLimits 分别测试后才组合。
- [ ] DynamicWorkflow 有采用或拒绝的测量依据。
- [ ] Pydantic Graph、domain validators 与 permission checks 未被替换。
- [ ] 原始 evidence retention 与模型 context limits 已分离。
- [ ] 生产 profile 只包含通过 gate 的 capabilities。

本章建议提交：

```text
ch08: evaluate and integrate selected harness capabilities
```

## 官方资料

- [Harness README](https://github.com/pydantic/pydantic-ai-harness)
- [Harness releases](https://github.com/pydantic/pydantic-ai-harness/releases)
- [Planning](https://pydantic.dev/docs/ai/harness/planning/)
- [Subagents](https://pydantic.dev/docs/ai/harness/subagents/)
- [Dynamic Workflow](https://pydantic.dev/docs/ai/harness/dynamic-workflow/)
- [Tool Output Limits](https://pydantic.dev/docs/ai/harness/tool-output-limits/)
