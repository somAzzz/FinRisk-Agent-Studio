# Pydantic AI 金融 Agent 完整学习指南

## 目标

这是一条横跨两个真实项目的十章实践路线：先在较小的 TCFD 文本项目里掌握 Pydantic AI Core，再在 FinRisk 项目里理解工具权限、专业 Agent、Harness 和生产治理。

整条路线的核心原则是：

> 不用 Agent 替代确定性软件。用 Pydantic AI 约束 LLM boundary，用 Harness 支撑开放式编排，同时保留证据验证、评分、图约束、权限和质量门禁的确定性与可审计性。

本指南整理自[分享对话](https://chatgpt.com/share/6a8b5705-fa54-83eb-9cc1-eca2ca71d925)，但不是逐字复制。分享内容包含当时可直接粘贴的答案代码和迁移前假设；本版本把它们改造成练习合同，并用 2026-08-23 的仓库状态与官方资料校正。

## 两个项目为什么分工不同

### `frequency_analyzer`：学习迁移

当前代码仍直接使用 OpenAI-compatible SDK，边界小而清晰：关键词抽取、共现相关性判断和总结生成。因此 Chapter 0–5 可以真实经历：

```text
Direct SDK
  -> typed Agent
  -> dependencies
  -> output validator
  -> programmatic workflow
  -> evals
```

### `fintext_llm`：学习生产结构与 Harness 扩展

当前项目已经完成 Pydantic AI 迁移，不再有分享对话所描述的 `src/llm/tool_loop.py`、legacy/shadow runtime 或可切回旧 runtime 的 feature flag。现状包括：

- `src/ai/model_factory.py`：集中 provider/model 工厂；
- `src/ai/deps.py`：`AgentDeps`、权限、预算、services；
- `src/ai/toolsets.py`：`FunctionToolset`、scoped filtering、结果 envelope 与 trace；
- `src/ai/agents/research.py`：typed market research Agent；
- `src/ai/agents/structured.py`：structured extraction/planner Agents 与 validators；
- `src/ai/runtime_adapter.py`：Pydantic AI 到现有 workflow contract 的适配；
- `src/ai/graphs/global_agent.py`：Pydantic Graph 的有界 planner/subgoal 状态机；
- `src/ai/approvals.py`：有过期和 replay protection 的服务端审批；
- `src/evaluation/`、`src/memory/`、`src/graph_reasoning/`：继续由项目掌握的领域治理。

所以 Chapter 6–9 应采用：

```text
阅读当前生产实现
  -> 在 tutorial_lab 隔离重建最小版本
  -> 写 contract/permission tests
  -> 比较设计差异
  -> 只在有证据时提出生产改进
```

## 十章知识地图

| 章 | 主要问题 | 最终产物 |
| --- | --- | --- |
| 0 | 本地模型真正支持哪些能力？ | 可重复 capability probe |
| 1 | 如何让输出成为 typed contract？ | Keyword Agent + 兼容适配器 |
| 2 | runtime object 与 prompt 如何分开？ | Typed deps + 动态 instructions |
| 3 | 如何把 grounding 变成可执行约束？ | 纯函数 validator + 有界 retry |
| 4 | 两个 Agent 如何由程序安全编排？ | Keyword → Python → Relevance |
| 5 | 如何验证迁移没有降低质量？ | 离线测试 + 30-case eval |
| 6 | 如何隔离工具能力与权限？ | Typed/scoped toolsets lab |
| 7 | 如何设计 evidence-first specialists？ | Typed findings + delegation lab |
| 8 | Harness 在 Core 之外增加什么？ | Planning/SubAgents/context 对比实验 |
| 9 | 如何进入可审计生产系统？ | 五层治理 + HITL + trace + parity eval |

## 最终目标架构

```text
User / API
  -> controlled workflow or bounded research entry
  -> Pydantic AI model + typed deps + scoped tools
  -> optional Harness capabilities for long tasks
  -> evidence candidates
  -> deterministic normalization and claim binding
  -> deterministic scoring / graph validation / critic
  -> project guardrails and human review
  -> deterministic report and trace API
```

模型负责发现、结构化和解释；Python 负责确认、权限、计量、评分和发布。

## 纠正分享对话中的过时点

1. FinRisk 的 Pydantic AI 迁移已经完成；不要建立 legacy feature flag，也不要恢复旧 tool loop。
2. 当前 `RiskAgent`、`CriticAgent` 和 `ReportAgent` 是确定性组件，不应为了“多 Agent”改成 LLM Agent。
3. 图解释必须基于工具返回的已验证路径；缺少路径代表 missing information，不代表关系不存在。
4. Harness 当前是独立的 0.x capability library，API 可在 minor 版本变化。练习必须锁版本并提交 lockfile。
5. Harness memory 是 Agent notebook，不是 FinRisk 的 evidence store。
6. Harness approval/HITL 不能代替服务端 authentication、authorization、expiry 和 replay protection。
7. 旧版“legacy vs Harness”比较已不适用。当前应比较 Pydantic AI Core baseline 与 Core + Harness，并确保现有 workflow contract 不退化。

## 学习分支

- `frequency_analyzer`：`tutorial/pydantic-ai`
- `fintext_llm`：`tutorial/pydantic-ai-harness`

不要把十章堆成一个大提交。每章通过验收后再提交并可选打 tag，利用 `git diff tutorial-chNN tutorial-chMM` 复习概念增量。

## 练习代码的边界

本教程不会给出以下主体实现：

- model factory；
- Agent 构造函数内容；
- tools 与 toolsets 函数体；
- validators；
- delegation tools；
- eval evaluators；
- Harness capability 组合；
- trace adapter。

章节只给输入输出合同、失败语义、测试要求和提示。你可以阅读生产代码核对，但建议先独立完成最小版本，再对照答案；否则练习会退化为抄写。

## 统一验收维度

每章至少从以下维度选择适用项：

- correctness：结构和业务不变量；
- grounding：结论是否绑定证据；
- capability isolation：不该出现的工具是否不可见且不可调用；
- budget：request/tool/token/业务预算；
- failure semantics：失败、降级和 review 是否可区分；
- observability：消息、tool event、usage、latency、guardrail verdict；
- compatibility：现有 API、workflow、fixtures 和 report 是否保持；
- privacy/security：凭据、SSRF、写门禁、审批和 trace redaction。

## 官方资料

- [Pydantic AI Core](https://ai.pydantic.dev/)
- [Models 与 OpenAI-compatible provider](https://ai.pydantic.dev/models/openai/)
- [Dependencies](https://ai.pydantic.dev/dependencies/)
- [Output](https://ai.pydantic.dev/output/)
- [Toolsets](https://ai.pydantic.dev/toolsets/)
- [Multi-agent applications](https://ai.pydantic.dev/multi-agent-applications/)
- [Usage limits](https://ai.pydantic.dev/usage/)
- [Testing](https://ai.pydantic.dev/testing/)
- [Pydantic Evals](https://ai.pydantic.dev/evals/)
- [Deferred tools / approvals](https://ai.pydantic.dev/deferred-tools/)
- [Pydantic AI Harness](https://github.com/pydantic/pydantic-ai-harness)
- [Harness version policy](https://github.com/pydantic/pydantic-ai-harness#version-policy)

## 完成后的表达能力

你最终应能不依赖背诵代码解释：

1. 为什么 direct SDK → typed Agent 是边界升级，而不仅是封装替换；
2. 为什么 prompt、schema、output validator、guardrail 和 eval 不能混为一谈；
3. 为什么 specialist tool isolation 比“一个 Agent 拿所有工具”更安全；
4. 为什么 programmatic handoff、Agent delegation 和 Harness orchestration 是三种不同控制方式；
5. 为什么金融系统中 Agent memory 不等于 evidence；
6. 为什么 HITL approval 不等于 authorization；
7. 为什么 unsupported claim rate 比回答长度更重要。

