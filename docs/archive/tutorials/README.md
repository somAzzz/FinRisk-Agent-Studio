# FinRisk Pydantic AI 教程与迁移实验

> 归档说明：这里同时保留当前实现导读、历史迁移复盘和未获批准的领域迁移推演。
> FinRisk 当前架构、能力与路线仍以 `docs/ARCHITECTURE.md`、`docs/STATUS.md` 和
> `docs/ROADMAP.md` 为准。

本目录不再用一组章节同时表达“当前已实现”和“未来待施工”。它分为三条路线：

| 路线 | 位置 | 状态 | 适合用途 |
| --- | --- | --- | --- |
| 当前实现教程 | Chapter 0–9 | 按当前 `main` 复核 | 理解代码、合同、Graph、测试和生产边界 |
| Runtime 迁移实验 | [`migration/runtime/`](migration/runtime/README.md) | 历史可重演 | 学习如何切换调用方、删除旧 runtime 并建立门禁 |
| 气候领域迁移 | [`migration/climate/`](migration/climate/README.md) | 条件式推演，未进入路线 | 在 owner、许可和数据策略通过后规划跨仓库迁移 |

先读[完整学习指南](COMPLETE_GUIDE.md)。

## 如何选择路线

- 要理解现在的 FinRisk：阅读 Chapter 0–9，并在当前 `main` 运行每章的检查。
- 要学习从旧 tool loop 迁移到 Pydantic AI：在隔离学习分支上使用 runtime 迁移实验。
- 要评估 Harness：先阅读当前 Chapter 8，再使用独立决策实验；不预设必须引入依赖。
- 要重启气候披露方案：先过 Chapter 10 的重启门，否则 Chapter 11–16 只作归档设计参考。

## 当前实现教程（Chapter 0–9）

| 章节 | 当前主题 | 学习重点 |
| --- | --- | --- |
| [0. Local Model](00-local-model.md) | deployment factory、`ModelSettings`、配置解析和 live probe | 区分 where/what model、how to generate 与 how much work |
| [1. Typed Agent](01-typed-agent.md) | 专用 typed outputs 与 client adapters | 从 `result.output` 到领域/workflow state |
| [2. Dependencies](02-dependencies.md) | run identity、subject、permissions、services 和 budget | 理解 per-run 对象所有权与 composition root |
| [3. Validation](03-validation.md) | schema、output validator、`ModelRetry`、guardrail | 区分结构错误、可重试语义错误和业务降级 |
| [4. Programmatic Workflow](04-programmatic-workflow.md) | 三类 Pydantic Graph 与确定性 workflow | 明确模型与 Python 各自控制什么 |
| [5. Evals](05-evals.md) | 离线测试、golden cases、source gate、live acceptance | 区分架构、回归、协议和质量证据 |
| [6. Typed Toolsets](06-toolsets.md) | 当前 model factory、deps、catalog/toolset 和权限 | 理解双 schema 兼容现状和实际预算范围 |
| [7. Specialists](07-specialists.md) | 当前 typed Agents、adapters 与三类 Graph | 验证单一 runtime 与 deterministic domain 边界 |
| [8. Runtime Integration](08-harness.md) | 同步 adapter、消息恢复、stream projection 和编排取舍 | 说明为何当前没有采用 Harness |
| [9. Production](09-production.md) | 当前审批、memory、trace、eval、live acceptance 及缺口 | 区分已有证据与尚未实现的保证 |

当前验证起点：

```bash
uv sync
uv run python -m pytest -q tests/ai
```

## Runtime 迁移实验

Runtime 迁移材料不再伪装成当前实现说明。它们有三个入口：

1. [迁移总图](migration/runtime/MIGRATION_MAP.md)：职责替换、保留的领域资产和四个门禁。
2. [Cutover Playbook](migration/runtime/cutover-playbook.md)：从历史基线建立新边界、迁移调用方、删除旧 runtime。
3. [Harness 决策实验](migration/runtime/harness-evaluation.md)：以 Core/Pydantic Graph 为 baseline，逐项评估能力。

这条路线只能在隔离分支或独立 worktree 重演。当前 `main` 已完成 cutover，
不应重新恢复 `src/llm/` 或第二套运行时。

## 气候领域迁移

[气候迁移入口](migration/climate/README.md)将 Chapter 10–16 放在同一条条件式路线中：

```text
重启决策
  -> owner / license / data / provenance
  -> 领域合同
  -> 可回源摄取与召回
  -> typed evidence Agents
  -> 确定性 assessment 与产品接入
  -> shadow / release / rollback
```

未通过重启门时，这些文件不是 backlog，也不构成产品承诺。

## 资料状态语义

- **当前实现**：路径和行为在当前 `main` 可验证。
- **历史可重演**：依赖指定历史 commit，不能直接对当前代码执行。
- **条件式推演**：只有前置决策和治理门通过后才可转为施工计划。

## 版本与约束

- Python：`3.12`
- 当前 `pydantic-ai` / `pydantic-ai-slim`：以 `uv.lock` 为准；本次复核为 `2.27.1`。
- 当前未安装 `pydantic-ai-harness`；不因为保留迁移实验而引入生产依赖。
- typed Python 签名和 Pydantic model 是新合同真相源。
- LLM 负责发现、选择、结构化和解释；权限、预算、证据确认、评分和发布门保持确定性。
