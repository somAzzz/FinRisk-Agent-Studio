# 迁移实验索引

> 本目录保留迁移方法和验收门，不代表当前 `main` 尚需执行这些迁移。

| 实验 | 状态 | 入口 |
| --- | --- | --- |
| Pydantic AI runtime cutover | 已完成的历史迁移，可在旧 commit 重演 | [`runtime/`](runtime/README.md) |
| TCFD/climate domain migration | 未进入产品路线，只在重启门通过后可执行 | [`climate/`](climate/README.md) |

两条路线共享以下规则：

- 施工指令必须绑定明确的历史基线或获批工作包；
- 当前事实必须从 `main`、`uv.lock`、测试与状态文档重新验证；
- 新边界通过验收后删除旧实现，不保留永久双 runtime；
- 涉及跨仓库代码、词表或真实报告时，先通过许可、数据和 provenance 门；
- 任何发布结论都需要可重复的测试、eval、source gate 和 rollback 证据。

当前实现导读返回[Chapter 0–9](../README.md)。
