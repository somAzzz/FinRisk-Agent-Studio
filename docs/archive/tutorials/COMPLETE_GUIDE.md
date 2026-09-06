# FinRisk Pydantic AI 完整学习指南

## 这套材料的边界

这不是一条必须在当前 `main` 顺序执行的十七章施工计划。它包含三种性质不同的学习材料：

1. Chapter 0–9 解释当前 FinRisk 实现。
2. Runtime 迁移实验重演已完成的 Pydantic AI cutover。
3. Climate 迁移实验保留未进入路线的条件式架构推演。

详细状态和入口见[目录 README](README.md)。

## 推荐学习顺序

### 第一阶段：理解当前 runtime

按 Chapter 0–9 阅读当前代码，而不是先猜测应该新建哪些文件：

```text
0. deployment policy 与 model settings
1. typed Agent output
2. run-scoped dependencies
3. schema、validator、retry 与降级
4. programmatic workflow 与 Pydantic Graph
5. offline tests、golden cases 与 live acceptance
6. model/deps/toolset 生产边界
7. typed specialists、adapters 与 Graph
8. 消息恢复、stream projection 与编排选择
9. 审批、memory、trace、eval 与尚存缺口
```

这一阶段的目标是能分清：

- model factory 为什么只是 deployment/composition boundary；
- typed deps 为什么按 run 组装；
- typed output、workflow state 和领域结果为什么不是同一个模型；
- 权限、预算、证据和评分为什么不能只交给 prompt；
- programmatic handoff、Pydantic Graph 和 Agent delegation 各自拥有什么控制权。

### 第二阶段：重演 runtime cutover

只有当你需要学习“如何迁移”时，才进入
[`migration/runtime/`](migration/runtime/README.md)。

这一阶段不在当前 `main` 直接实施。它使用历史基线练习：

```text
盘点旧职责
  -> 建立新的 model/deps/tool/output 边界
  -> 迁移生产调用方
  -> 删除旧 runtime 和兼容分支
  -> source/import gate
  -> 回归、eval 和 live acceptance
```

具体执行见 [Cutover Playbook](migration/runtime/cutover-playbook.md)，职责替换见
[迁移总图](migration/runtime/MIGRATION_MAP.md)。

### 第三阶段：只在获批后重启 climate 迁移

[`migration/climate/`](migration/climate/README.md) 不是默认的下一个开发阶段。只有以下条件
都有 owner 和可验证证据时，Chapter 10–16 才可转成 backlog：

- 产品目标、用户和成功指标明确；
- 源代码与词表许可可追踪；
- 真实报告的存储、传输、provider 与保留政策获批；
- provenance manifest 能固定源 revision 和资产；
- 不引入跨仓库运行时依赖。

## 当前目标架构

```text
User / API / CLI
  -> authenticated application boundary
  -> programmatic workflow or Pydantic Graph
  -> typed specialist Agent
       -> centralized Model
       -> run-scoped Deps
       -> scoped Toolsets
       -> typed Output + validator
  -> evidence candidates
  -> deterministic normalization and claim binding
  -> deterministic scoring / graph validation / critic
  -> approval + quality gate + human review
  -> deterministic report + versioned trace
```

模型负责发现、选择、结构化和解释；Python 与存储层负责权限、事实确认、预算、
评分、审批、审计和发布。

## 迁移时必须保留的原则

### 应替换的 runtime 职责

- direct SDK completion 与手写 tool-call loop；
- provider/client 构造散落在业务模块；
- generic JSON result 和手工 repair；
- 一个 Agent 默认拿到所有工具；
- provider 失败时回到另一套 LLM runtime；
- 只靠日志和人工阅读判断迁移是否完成。

### 应保留或显式迁移的领域资产

- evidence、claim、relation 和 workflow models；
- deterministic risk scoring、graph validation、critic 和 report rendering；
- API/数据库中真正被产品消费的合同；
- authentication、authorization、SSRF 防护与安全脱敏；
- human review 与可审计审批；
- offline fixtures 与 golden cases。

“保留”不等于无条件兼容。合同需要改变时，应写 ADR、迁移调用方/数据并增加测试，
而不是在新架构内部偷偷接受所有旧输入。

## 三种编排不要混淆

| 模式 | 谁决定下一步 | 适合场景 | 不适合场景 |
| --- | --- | --- | --- |
| Programmatic handoff | Python | 固定业务流程、低成本、强审计 | 开放式探索 |
| Pydantic Graph | typed state + Python edges | 分支、checkpoint、明确停止条件 | 单步抽取 |
| Agent delegation | 模型在受限能力内 | 开放式研究、动态子问题 | 资金/写操作、不可绕过的质量门 |

Harness 只能在独立实验证明增益后加入；它不是默认第四种运行时。

## 五类验证证据

| 层 | 工具 | 证明什么 |
| --- | --- | --- |
| model/schema | Pydantic tests | 结构与局部不变量 |
| agent/tool | `TestModel`、`FunctionModel` | schema exposure、调用路径、retry、权限 |
| workflow | fake services + Graph tests | 状态转换、预算、失败、quality gate |
| migration/eval | 固定 fixtures | grounding、工具选择、成本、trace parity |
| live acceptance | 真实 provider | structured output、tool calling、usage 协议能力 |

不能用 live smoke 代替离线回归，也不能用 `TestModel` 的答案质量推断真实模型质量。

## 完成标准

学习者应能不依赖背诵代码回答：

1. typed Agent 为什么是边界重设，而不是 SDK wrapper；
2. typed tool 签名为什么应是 schema 真相源；
3. 工具已做 visibility filtering 后为什么仍要 execution-time authorization；
4. 哪些旧接口已删除，哪些领域合同被保留；
5. 测试、eval、live acceptance 和 source gate 各自能证明什么；
6. 为什么历史迁移实验不能被误当成当前路线。
