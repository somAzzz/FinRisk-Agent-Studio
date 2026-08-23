# Chapter 8：Harness Capabilities 与长任务编排

## 学习目标

理解 Pydantic AI Core 与 Pydantic AI Harness 的边界，实验 Planning、SubAgents、ToolOutputLimits 等 capabilities 是否能改善长任务编排，而不破坏现有 Pydantic Graph workflow 和领域规则。

## 版本与稳定性提醒

本仓库当前没有安装 `pydantic-ai-harness`。官方 Harness 是独立的 0.x capability library，minor 版本可能修改参数、默认值和结构。

开始本章时必须：

1. 阅读官方 [README](https://github.com/pydantic/pydantic-ai-harness) 与 release notes；
2. 选择并精确锁定一个与当前 Pydantic AI 兼容的版本；
3. 提交 `uv.lock`；
4. 用最小 import/capability smoke 验证当前 API；
5. 若 API 与本文术语不同，记录版本差异，而不是复制旧示例。

截至本教程校对时，官方包仍导出 `Planning`、`SubAgent`、`SubAgents`、`Memory`、`ToolOutputLimits` 和 guardrail capabilities，但构造参数应以你锁定版本为准。

## Harness 解决什么

Pydantic AI Core 已提供 typed agent loop、models、tools、deps、output、usage 和消息。Harness 通过可组合 capabilities 增加长任务常用能力，例如：

- model-owned planning；
- sub-agent delegation；
- persistent notebook memory；
- tool-output/context 管理；
- input/output/tool guardrails；
- compaction、skills 或 dynamic workflow。

Harness 不替代 FinRisk 的 evidence store、业务状态机、审批数据库、quality gate 或 API contract。

## 当前 baseline

先阅读：

- `src/ai/graphs/global_agent.py`：有界 planner → subgoal → planner 图；
- `src/agents/planner.py`：structured decision 与 fallback；
- `src/ai/runtime_adapter.py`：subgoal Agent run 与 usage limits；
- `src/agents/state.py`：budget、trace、human review；
- `docs/PYDANTIC_AI_MIGRATION.md`：迁移已完成的事实。

当前 baseline 是 Pydantic Graph + Pydantic AI Core，不是 legacy tool loop。

## 练习 8.1：建立 Harness smoke lab

在 `tutorial_lab/ch08/` 创建一个不接生产 API 的最小 Agent，逐个加入 capability：

1. 无 Harness 的 Core Agent；
2. 只加 Planning；
3. 加 SubAgents；
4. 加 ToolOutputLimits；
5. 最后组合。

每一步都记录：model requests、tool calls、tokens、latency、输出质量和 trace 可读性。不要一次全加后猜测哪个 capability 起作用。

## 练习 8.2：Planning

设计一个至少三步的金融研究任务，观察：

- 是否创建计划；
- task 状态是否更新；
- 失败后是否重规划；
- 计划是否导致重复搜索；
- 简单任务是否产生不必要规划开销；
- plan 是否能进入现有 trace，而不是只存在模型上下文。

计划是执行辅助信息，不是 evidence，也不能替代 workflow checkpoint。

## 练习 8.3：SubAgents

复用 Chapter 7 的 specialists。要求：

- coordinator 给 child 的 task 自包含；
- child 具有独立 message history；
- deps 传递规则明确；
- 每个 child 配置 budget、timeout、max calls；
- parent 能区分 completed、needs_review、timeout 和 failed；
- specialist output 仍进入现有 evidence/quality layer。

比较 Core delegation 与 Harness SubAgents：代码量、模型轮次、上下文污染、budget 归集和失败隔离分别如何变化？

## 练习 8.4：ToolOutputLimits

用一个 fake filing tool 返回超长文本，验证：

- 大结果不会无限进入 context；
- 原始完整结果是否保留在可审计存储；
- 模型是否可按需读取片段；
- truncation/spill 事件是否映射到项目 trace；
- quote/citation 不会引用已丢失文本。

不要把 context protection 与 evidence retention 混为一谈。模型上下文可以受限，审计证据不应因此永久丢失。

## 练习 8.5：预算双层模型

区分：

- 框架 usage limits：requests、tool calls、tokens、cost；
- 业务预算：最多几家公司、几个供应链路径、多少来源、总运行时间；
- capability 自身预算：每个 sub-agent 的 calls/timeout；
- context limits：单次与累计 tool result。

把它们映射到现有 `AgentBudget`，标出哪些能直接适配，哪些必须留在 domain layer。

## 练习 8.6：Core vs Harness 对比

使用同一 fixtures 和任务，对比：

```text
Pydantic Graph + Core baseline
vs
Core + selected Harness capabilities
```

至少衡量：

| 指标 | 为什么重要 |
| --- | --- |
| model requests | 编排成本 |
| tool calls / duplicates | 工具选择效率 |
| accepted evidence | 有效产出 |
| unsupported claims | 核心安全指标 |
| source diversity | 研究质量 |
| human-review items | 是否过度或不足复核 |
| tokens / latency | 资源与体验 |
| existing trace completeness | 前端/API 兼容 |

## DoD

- [ ] Harness 版本已精确锁定并记录。
- [ ] capabilities 逐个验证，不是一次性黑盒组合。
- [ ] Planning 能运行且计划不被当作 evidence。
- [ ] SubAgents 能委派且每个 child 有 budget/timeout。
- [ ] 大 tool output 受控，完整证据仍可审计。
- [ ] 现有 Pydantic Graph baseline 仍可运行。
- [ ] Core 与 Harness 使用同一 fixtures 比较。
- [ ] Harness 没有替代 domain logic。

## 面试题

Pydantic AI Core 给出 typed Agent 基础；Harness 给出可组合的长任务 capabilities。引入 Harness 的理由必须来自测量到的编排、上下文或维护收益，而不是因为它“更高级”。

