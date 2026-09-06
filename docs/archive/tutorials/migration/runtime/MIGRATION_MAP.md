# 迁移总图：从旧 tool loop 到 Pydantic AI 架构

> 历史迁移复盘。本文只描述 Chapter 6–9 对应的 Agent runtime cutover，
> 不是要求在当前 `main` 重新引入旧 runtime。气候披露的条件式迁移见
> [气候迁移总图](../climate/MIGRATION_MAP.md)。

## 为什么需要这张图

只看当前完成态，很难训练真实重构中最重要的三件事：确定新合同、
切换生产调用方、删除旧实现。因此这张图保留累计迁移视角，并与
[当前 Chapter 6–9](../../README.md)形成“过程—结果”对照。

## 起点与终点

练习基线：`023c02f91be43ecf6428d12e5dac3272569a62b3`。

该提交仍包含：

- `src/llm/tool_loop.py` 的自定义 OpenAI tool-call loop；
- `src/agents/runtime.py` 与 `src/agents/llm_runtime.py` 的手写运行时；
- 多个 `parse` / `complete` / generic JSON client；
- workflow 中由业务代码直接处理模型失败、JSON 修复和 fallback 的混合职责。

目标不是保持这些 Python 接口可用，而是建立以下结构：

```text
API / CLI
  -> application workflow / Pydantic Graph
  -> typed specialist Agent
       -> centralized model factory
       -> typed per-run dependencies
       -> scoped typed toolsets
       -> typed output + output validators
  -> evidence normalization and claim binding
  -> deterministic scoring / graph validation / quality gate
  -> trace, approval, persistence and human review
```

## 职责替换表

“替代”指职责迁移，不要求新旧类一一对应。

| 旧职责/文件 | 新职责/文件 | 迁移完成判据 |
| --- | --- | --- |
| `src/llm/client.py`、`deepseek_client.py`、`sglang_client.py` 分散构造客户端 | `src/ai/model_factory.py` | provider/model/base URL/API key 只在一个工厂解析 |
| `src/llm/tool_loop.py` 手写消息循环、tool call、重试 | Pydantic AI `Agent` + `src/ai/toolsets.py` + `UsageLimits` | `src/` 不再出现自定义 OpenAI tool-loop 方法 |
| `src/tools/contracts.py` 中面向旧 loop 的 JSON schema | typed tool 函数签名与 Pydantic constraints | 模型 schema 由 Python 类型生成；旧 schema 不再是真相源 |
| `src/agents/runtime.py`、`src/agents/llm_runtime.py` | `src/ai/runtime_adapter.py` 与 Pydantic Graph | workflow 只依赖新的 typed result contract |
| generic `parse` / `complete` / 手工 JSON repair | `src/ai/agents/structured.py` + typed clients | 每个模型边界返回专用 Pydantic model |
| 手写全局 planner/subgoal while-loop | `src/ai/graphs/global_agent.py` | 节点、边、停止条件和预算可测试 |
| workflow 内散落的 provider/fallback 判断 | composition root + 明确的确定性降级 | provider 故障不会切回另一套 LLM runtime |
| 临时权限检查 | `AgentPermissions` + tool 可见性过滤 + 执行时复核 | 绕过 schema 直接执行仍被拒绝 |
| 模型输出直接进入报告 | evidence normalization、claim binding、quality gate | specialist output 不能绕过确定性质量层 |

## 需要保留的领域资产

真正重构不等于全部重写。以下代码的确定性性质是架构资产：

- `src/schemas/` 的 evidence、claim、relation、workflow models；
- `src/evaluation/` 的 grounding、安全、source quality 与 workflow validators；
- `src/graph_reasoning/` 的路径检索、评分、绑定与验证；
- `src/agents/risk_agent.py`、`critic.py`、`report_agent.py` 的确定性职责；
- API payload、持久化格式和前端 trace 中仍被产品使用的字段。

保留这些合同是业务选择，不是为了让旧 runtime 继续存在。若你有证据证明某个合同也应
重设，应写 ADR、迁移数据和调用方，而不是增加隐式 adapter。

## 四个迁移关口

### Gate A：新边界独立成立（Chapter 6）

新 model/deps/toolset 可在没有旧 tool loop 的测试中独立运行；权限、失败语义、usage
和 trace 都有合同测试。

### Gate B：生产调用方完成切换（Chapter 7）

所有模型驱动路径使用 typed Agent；旧 runtime、generic JSON client 与对应测试被删除；
仓库级 import/source scan 防止重新引入。

### Gate C：Harness 有测量依据（Chapter 8）

当前结论是保留 Core/Pydantic Graph，不安装 Harness。未来只能在有可重复缺口时，
按 [Harness 决策实验](harness-evaluation.md)逐项对比；没有净收益的 capability 不进入生产组合。

### Gate D：生产治理闭环（Chapter 9）

安全规则分层、审批可防 replay、memory 不会晋升为事实、trace 可关联、离线 eval 可比较，
才允许发布。

## 禁止的伪迁移

- 新建 Pydantic Agent，但内部仍调用旧 `complete()`；
- typed output 外再做“尽力修复 JSON”；
- 用 `AGENT_RUNTIME_MODE` 长期保留两套 runtime；
- tool 在 schema 中隐藏，但可被编程调用绕过；
- Harness memory 直接写入 evidence store；
- 用 Harness approval 代替服务端 authentication/authorization；
- 新旧实现测试都通过，却没有任何测试证明旧实现不可达。

## 最终 source gate

完成 Chapter 7 后至少增加一个仓库级检查，表达以下意图：

```text
src/ 中不存在旧 runtime 文件；
业务模块中不存在直接 chat.completions 调用；
不存在 parse/complete 兼容分支；
所有 Agent 都声明 deps_type 与 typed output；
所有生产 toolset 都经过 scope 与 execution-time permission check。
```

Chapter 9 再以全量测试、live acceptance 和 source gate 作为最终证据。只有实际运行了
Harness 实验时，才增加 Core/Harness 对比报告。
