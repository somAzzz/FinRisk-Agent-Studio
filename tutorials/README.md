# FinRisk Pydantic AI / Harness 教程（Chapter 6–9）

这里是十章学习路线的后半程，使用 `FinRisk Agent Studio` 学习 typed toolsets、specialist agents、Harness capabilities 与生产治理。

请先读[完整学习指南](COMPLETE_GUIDE.md)。该文档是对原始分享对话的完整整理和现实校正；各章节文件是可执行的练习说明。

## 当前分支与定位

- 分支：`tutorial/pydantic-ai-harness`
- 当前生产基线：Pydantic AI 已完成迁移
- 本地版本：`pydantic-ai-slim 2.33.0`
- 当前未安装：`pydantic-ai-harness`、`pydantic-evals`
- 本教程变更：仅文档，不实现练习代码、不添加依赖

Chapter 6–9 不是让你再迁移一次已经删除的 legacy runtime。推荐在自己练习时使用隔离目录 `tutorial_lab/` 重建最小版本，再与 `src/ai/` 的生产实现比较；只有形成明确设计结论后，才考虑对生产代码做增量改动。

## 章节

1. [Chapter 6：Typed Toolsets 与权限边界](06-toolsets.md)
2. [Chapter 7：Specialist Agents 与 Delegation](07-specialists.md)
3. [Chapter 8：Harness Capabilities 与长任务编排](08-harness.md)
4. [Chapter 9：生产治理与迁移评估](09-production.md)

Chapter 0–5 位于本地 `/home/bo/projects/python/frequency_analyzer/tutorials/`，对应分支 `tutorial/pydantic-ai`。GitHub 上可从 [llm_tcfd tutorial 分支](https://github.com/somAzzz/llm_tcfd/tree/tutorial/pydantic-ai/tutorials)查看。

## 建议提交

```text
ch06: reconstruct typed toolsets and permission tests
ch07: add isolated typed specialist agent lab
ch08: compare core orchestration with harness capabilities
ch09: integrate layered guardrails memory hitl and evals
```

提交名只是建议。代码未完成前不要创建 `tutorial-ch06` 至 `tutorial-ch09` tag。

