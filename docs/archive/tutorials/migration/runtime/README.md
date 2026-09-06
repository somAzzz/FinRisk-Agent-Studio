# Runtime 迁移实验

> 状态：历史可重演。当前 `main` 已经只有 Pydantic AI runtime。

这条路线保留 tutorial 分支中最有教学价值的迁移内容，但不保留过时依赖版本、
不存在的“当前文件”或必须引入 Harness 的预设。

## 入口

- [迁移总图](MIGRATION_MAP.md)：从旧职责到当前边界的映射。
- [Cutover Playbook](cutover-playbook.md)：分阶段切换、删除与验收。
- [Harness 决策实验](harness-evaluation.md)：将 Harness 当作候选能力，而不是迁移目标。
- [Chapter 6](../../06-toolsets.md) 与 [Chapter 7](../../07-specialists.md)：对照当前完成态。
- [Chapter 8](../../08-harness.md) 与 [Chapter 9](../../09-production.md)：对照当前编排与生产治理边界。

## 历史基线

```text
练习起点: 023c02f91be43ecf6428d12e5dac3272569a62b3
当前对照: 以学习当时 origin/main 为准
```

建议在独立 worktree 或可随时丢弃的学习分支上重演。不要在当前 `main` 中恢复旧
`src/llm/` 或新增长期 runtime feature flag。

## 实验边界

这里训练的是迁移技术：合同重设、调用方切换、短期双路径控制、源码删除和
机械门禁。它不要求追求与历史 commit 字节级一致，也不允许为通过旧测试而保留
永久兼容层。
