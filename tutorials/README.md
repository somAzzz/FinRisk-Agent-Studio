# FinRisk Pydantic AI / Harness 重构教程（Chapter 6–9）

这四章不是在现有代码旁边再做一套演示，也不是给旧 runtime 套兼容层。目标是从
迁移前的真实仓库出发，完成一次可运行、可删除旧代码、可通过回归测试的 Pydantic AI
架构重构。

先读[完整学习指南](COMPLETE_GUIDE.md)和[迁移总图](MIGRATION_MAP.md)，再按顺序完成
Chapter 6–9。每章都明确列出新建、修改和删除的文件，以及它们接替的旧职责。

## 推荐起点

当前分支已经包含最终实现，适合对照答案，不适合直接练习。推荐从第一次 Pydantic AI
提交之前的提交创建学习分支：

```bash
git switch -c learn/pydantic-ai-refactor \
  023c02f91be43ecf6428d12e5dac3272569a62b3
uv sync
uv run pytest -q
```

不要在开始前阅读后续迁移提交的实现。完成每章并通过验收后，再用当前 `main` 或
`tutorial/pydantic-ai-harness` 分支作设计对照。

## 章节与累计产物

| 章节 | 核心结果 | 主要替代对象 |
| --- | --- | --- |
| [6. Typed Toolsets](06-toolsets.md) | model factory、typed deps、typed tools、权限与 trace | 业务代码直接选择 provider、手写工具 schema、`src/llm/tool_loop.py` 的工具执行职责 |
| [7. Specialists](07-specialists.md) | typed specialist Agents、Pydantic Graph、正式 cutover | generic JSON/completion client、手写 planner/tool loop、自由文本 Agent 边界 |
| [8. Harness](08-harness.md) | Core baseline 与选定 Harness capabilities 的实测集成 | 只替代被实验证明冗余的编排/上下文辅助代码，不替代领域状态机 |
| [9. Production](09-production.md) | guardrails、审批、memory 隔离、trace、eval 与发布门禁 | 临时安全检查、不可审计审批、把 memory 当 evidence、人工目测迁移质量 |

四章是同一条分支上的累计重构，不再创建互不相干的 `tutorial_lab/ch06`、`ch07`。

## 实施约束

- typed Python 签名和 Pydantic model 是新合同的真相源，不从旧 JSON schema 反向生成。
- 只保留明确列出的领域/API 合同；不为旧 Python 类、旧调用参数或旧 runtime flag
  创建长期兼容层。
- 新路径通过验收后删除旧实现与旧测试，禁止保留双 runtime。
- LLM 负责发现、选择、结构化和解释；证据确认、权限、预算、评分、图校验和发布门禁
  仍由确定性代码负责。
- 教程提供合同、实现顺序和测试要求，不提供可直接复制的主体答案代码。

## 版本基线

- Python：`3.12`
- 当前 Pydantic AI 锁定版本：`pydantic-ai-slim 2.33.0`
- Chapter 8 建议实验版本：`pydantic-ai-harness 0.27.0`
- Harness 仍为 `0.x`；升级 minor 版本前必须读 release notes 并重跑 Chapter 8–9
  的 contract/eval tests。

版本信息校对日期为 2026-08-31。实际实现时以 `uv.lock` 与官方文档为准。

## 每章提交建议

```text
ch06: establish typed model deps and tool boundaries
ch07: cut over to typed specialist agents and graphs
ch08: evaluate and integrate selected harness capabilities
ch09: add production governance trace and migration evals
```

每章只在 DoD 全部通过后提交。Chapter 7 的提交必须能证明旧 runtime 已被真正删除，
而不是被 feature flag 隐藏。
