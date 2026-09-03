# Pydantic AI 金融 Agent 完整学习指南

## 学习目标

这是一条跨两个真实项目的三阶段十七章路线。Chapter 0–5 在较小的文本分析项目里掌握
Core；Chapter 6–9 在 FinRisk 中完成真实架构切换、删除旧 runtime，并用 Harness 实验和
生产治理收尾；Chapter 10–16 再把 TCFD 研究资产迁成 FinRisk 的气候披露领域能力。

目标不是“尽量不动旧 pipeline”，也不是把 Pydantic AI 藏在兼容 adapter 后面。目标是：

> 重新定义模型边界，迁移所有调用方，删除旧实现，并保留真正属于领域层的确定性约束。

## 两个项目的分工

### Chapter 0–5：Core 基础

`frequency_analyzer` 适合学习：

```text
0. provider capability probe
1. typed Agent output
2. typed dependencies and dynamic instructions
3. output validator and bounded retry
4. programmatic workflow
5. offline tests and evals
```

对应内容位于 `frequency_analyzer` 的 `tutorial/pydantic-ai` 分支；远程参考：
[llm_tcfd tutorials](https://github.com/somAzzz/llm_tcfd/tree/tutorial/pydantic-ai/tutorials)。

进入 Chapter 6 前，你应能独立解释：

- schema validation、output validator、guardrail、eval 的区别；
- model factory 为什么属于 infrastructure/composition boundary；
- deps 为什么是 run-scoped，而不是装所有对象的全局容器；
- `TestModel`、`FunctionModel` 和 live model 分别验证什么；
- programmatic handoff 为什么比“让 coordinator 自己决定一切”更可预测。

### Chapter 6–9：真实 FinRisk 重构

当前主分支已经完成 Pydantic AI 迁移，因此它是结果参考。真正练习应从迁移前基线
`023c02f91be43ecf6428d12e5dac3272569a62b3` 新建分支，直接修改真实 `src/` 和
`tests/`，而不是创建互不相干的 lab。

```bash
git switch -c learn/pydantic-ai-refactor \
  023c02f91be43ecf6428d12e5dac3272569a62b3
uv sync
uv run pytest -q
```

这一安排让你真实经历：新边界与旧 runtime 暂时并存 → 逐路径切换 → 删除旧 runtime →
用 source/import gate 防止回归。短暂并存是迁移步骤，不是最终兼容目标。

### Chapter 10–16：气候披露领域合并

这部分不再练习 SDK/runtime 切换，而是在已经统一的 Pydantic AI 基础设施上实现新领域：

```text
10. repository boundary, licensing and provenance
11. document/evidence/requirement contracts
12. traceable multi-market ingestion
13. reviewed registry and hybrid retrieval
14. typed evidence extraction and verification
15. deterministic assessment and product integration
16. layered eval, shadow run and cutover
```

参考起点是 FinRisk `145e34b2...` 与 TCFD `4ef1c0f4...`。完整 SHA、源/目标文件映射和
不迁移项见[气候披露迁移总图](CLIMATE_MIGRATION_MAP.md)。领域实现目前是教程目标，不能把
合并方案误写成现成功能。

## 十七章知识地图

| 章 | 主要问题 | 最终产物 |
| --- | --- | --- |
| 0 | 本地模型真正支持哪些能力？ | 可重复 capability probe |
| 1 | 如何让输出成为 typed contract？ | typed Agent + domain output |
| 2 | runtime object 与 prompt 如何分开？ | typed deps + dynamic instructions |
| 3 | 如何把 grounding 变成可执行约束？ | 纯函数 validator + bounded retry |
| 4 | 多个 Agent 如何安全组合？ | programmatic workflow |
| 5 | 如何证明重构没有降低质量？ | offline tests + eval dataset |
| 6 | 如何建立生产模型与工具边界？ | model factory + deps + scoped typed toolsets |
| 7 | 如何完成真实 cutover？ | typed specialists + Pydantic Graph + 删除旧 runtime |
| 8 | Harness 哪些能力值得采用？ | Core/Harness 对比 + selected capability profile |
| 9 | 如何进入可审计生产系统？ | layered guardrails + HITL + memory policy + trace + release gates |
| 10 | 如何在两个仓库之间保持单一所有权？ | provenance + license/data gate + architecture test |
| 11 | 如何区分候选、证据、映射与最终状态？ | versioned climate contracts + independent state |
| 12 | 如何让中英文报告片段精确回源？ | disclosure adapters + blocks/locators/issues |
| 13 | 如何从标准要求而不是词袋出发召回？ | registry + multi-channel retrieval |
| 14 | Pydantic AI 在气候评审中负责什么？ | typed extractor + verifier，确定性 locator/metric gate |
| 15 | 如何把证据变成可审计产品结果？ | deterministic assessment + report/API/UI/HITL |
| 16 | 如何证明迁移质量并安全切换？ | layered eval + shadow + release/rollback |

## 目标架构

```text
User / API / CLI
  -> authenticated application boundary
  -> programmatic workflow or Pydantic Graph
  -> typed specialist Agent
       -> centralized Model
       -> run-scoped Deps
       -> scoped Toolsets
       -> typed Output + validator
       -> selected Harness capabilities (optional)
  -> evidence candidates
  -> deterministic normalization and claim binding
  -> deterministic scoring / graph validation / critic
  -> guardrails + quality gate + human review
  -> deterministic report + versioned trace
```

模型负责发现、选择、结构化和解释；Python/存储层负责权限、事实确认、预算、评分、审批、
审计和发布。

## 重构时什么可以变，什么必须有理由

### 应主动替换

- direct SDK completion 与手写 tool-call loop；
- provider/client 构造散落在业务模块；
- generic JSON result 和手工 repair；
- `hasattr(parse/complete)` 式 client 兼容；
- 一个 Agent 默认拿所有工具；
- 手写且难以测试的 planner/step while-loop；
- provider 失败时切回另一套 LLM runtime；
- 只靠日志和人工阅读判断迁移是否成功。

### 应保留或显式迁移

- evidence、claim、relation 等领域 schema；
- deterministic risk scoring、graph validation、critic、report rendering；
- API/数据库中真正被产品消费的合同；
- authentication、authorization、SSRF、安全脱敏；
- human review 与可审计审批；
- offline fixtures 与黄金案例。

“保留”不是无条件兼容。如果新设计需要改变这些合同，应写 ADR、迁移调用方/数据并测试，
而不是在新架构内部偷偷接受所有旧输入。

## 三个阶段如何累计

### Chapter 6：建立新边界

先让新的 Model/Deps/Toolsets 在 `TestModel`/`FunctionModel` 下独立成立。此时旧 runtime
仍为未迁移调用方服务，但新代码不调用它。

### Chapter 7：切换并删除

创建 typed specialists 和 Graph，逐条迁移 filing、market、browser、supply chain、global
research、API/CLI。每迁移一路就删除对应旧分支；最后删除整个旧 runtime 和旧测试。

### Chapter 8：测量 Harness

Core/Pydantic Graph 是 baseline。逐项加入 Planning、SubAgents、ToolOutputLimits 和可选
DynamicWorkflow；只保留通过质量、成本、权限和 trace gate 的 capability。Harness 是
同一个 Pydantic AI Agent 的扩展，不是第二套 runtime。

### Chapter 9：生产闭环

完成 guardrail 分层、server-side approval、memory promotion policy、trace adapter、30-case
eval、live acceptance、ADR 和 runbook。发布失败时回滚部署 revision，不恢复旧代码分支。

### Chapter 10–11：先固定迁移边界和新合同

先解决 source/license/data policy 和跨仓库依赖，再定义 document、evidence、requirement、mapping、
metric、assessment 与独立 workflow state。此时不搬词表、不调用模型。

### Chapter 12–14：建立证据生产链

统一 SEC/TXT/A 股/PDF 文档块和 locator，以经过审核的 registry 驱动混合 retrieval，再用两个
typed Agent 完成 evidence proposal 和逐 mapping verification。quote/hash/metric 仍由确定性代码
校验。

### Chapter 15–16：产品闭环与切换

用纯规则聚合五状态，接入报告、API、人工审核和前端，然后建立分层 eval 与旧流程 shadow。
通过机械追溯门、质量阈值、数据审核和回滚演练后，才切换默认入口。

## 三种编排不要混淆

| 模式 | 谁决定下一步 | 适合场景 | 不适合场景 |
| --- | --- | --- | --- |
| Programmatic handoff | Python | 固定业务流程、低成本、强审计 | 开放式探索 |
| Pydantic Graph | typed state + Python edges | 分支、并行、checkpoint、明确停止条件 | 单步抽取 |
| Agent delegation / Harness | 模型在受限能力内 | 开放式研究、动态子问题 | 资金/写操作、不可绕过的质量门禁 |

同一个系统可以同时使用三者，但每层必须有明确所有权。不要用 Harness Planning 表示业务
workflow state，也不要用 Pydantic Graph 把每个普通函数机械包装成节点。

## 五类验证证据

| 层 | 工具 | 证明什么 |
| --- | --- | --- |
| model/schema | Pydantic tests | 结构与局部不变量 |
| agent/tool | TestModel、FunctionModel | schema exposure、调用路径、retry、权限 |
| workflow | fake services + Graph tests | 状态转换、预算、失败、quality gate |
| migration/eval | 固定 30-case fixtures | grounding、工具选择、成本、trace parity |
| live acceptance | 真实 provider | 真实 structured output/tool calling/usage 能力 |

不能用 live smoke 代替离线回归，也不能用 `TestModel` 的答案质量推断真实模型表现。

## 统一质量指标

每章从以下维度建立适用 gate：

- correctness：typed contract 与业务不变量；
- grounding：结论是否绑定可验证证据；
- capability isolation：不可见工具是否也无法执行；
- budget：request/tool/token/domain/deadline；
- failure semantics：provider、validation、guardrail、domain、review 可区分；
- observability：message、tool、plan、delegation、usage、latency、verdict 可关联；
- security/privacy：secret、SSRF、tenant、write、approval、trace redaction；
- migration completeness：旧 runtime 不可达且源代码已删除；
- operational readiness：live gate、ADR、runbook、rollback revision。

最重要的质量门禁是 unsupported claim rate 不恶化；回答更长、计划更漂亮、Agent 更多都
不是成功标准。

## 版本策略

本教程在 2026-08-31 对照：

- `pydantic-ai-slim 2.33.0`（当前 lock）；
- `pydantic-ai-harness 0.27.0`（Chapter 8 建议实验 pin）。

Harness 的 `0.x` minor release 允许 breaking changes。实现 Chapter 8 前阅读
[官方 releases](https://github.com/pydantic/pydantic-ai-harness/releases)，精确 pin 版本并
提交 lockfile。教程中的概念合同优先于某个旧构造函数拼法；API 变化时更新实现和测试，
不要用 `Any`、忽略异常或复制兼容 wrapper 掩盖差异。

## 官方资料

- [Pydantic AI](https://pydantic.dev/docs/ai/)
- [Dependencies](https://pydantic.dev/docs/ai/core-concepts/dependencies/)
- [Output](https://pydantic.dev/docs/ai/core-concepts/output/)
- [Toolsets](https://pydantic.dev/docs/ai/tools-toolsets/toolsets/)
- [Testing](https://pydantic.dev/docs/ai/guides/testing/)
- [Pydantic Graph](https://pydantic.dev/docs/ai/graph/)
- [Pydantic Evals](https://pydantic.dev/docs/ai/evals/)
- [Pydantic AI Harness](https://github.com/pydantic/pydantic-ai-harness)
- [Harness version policy](https://github.com/pydantic/pydantic-ai-harness#version-policy)

## 完成后的自检

你应能不依赖背诵代码回答：

1. typed Agent 为什么是边界重设，而不是 SDK 包装；
2. 为什么 typed tool 签名应成为 schema 真相源；
3. 为什么 visibility filtering 后仍要 execution-time authorization；
4. 哪些旧接口被删除，哪些领域合同被保留，理由是什么；
5. programmatic handoff、Graph、delegation、DynamicWorkflow 各自的控制权；
6. 为什么 Harness memory 不能直接成为 evidence；
7. 为什么 deferred approval 不能替代 authorization；
8. 如何用测试、eval、live acceptance 和 source gate 共同证明迁移完成。
9. 为什么 `EvidenceCandidate.accepted` 不能直接成为 `ClimateEvidence` 或 `present`；
10. 为什么 policy/market/technology/reputation 不是 TCFD 四支柱；
11. 为什么 Agent 负责 evidence/verdict，而最终 requirement 状态必须确定性聚合；
12. 如何用 provenance、shadow 和 rollback 证明跨仓库合并可审计。
