# 候选发布审计

执行日期：2026-07-11

结论：**暂不建议创建 `v0.1.0` tag**。数据迁移、财务勾稽和自动化回归已达到候选标准，但真实浏览器验收仍阻塞，Peer Analysis 与默认 FinRisk 启动仍有产品交付项。

## 已通过

| 门禁 | 结果 | 证据 |
| --- | --- | --- |
| 后端全量测试 | 通过 | `962 passed, 7 skipped` |
| 前端测试 | 通过 | 17 files，64 tests |
| TypeScript 与生产构建 | 通过 | `tsc -b`、Vite production build |
| Golden cases | 通过 | 30/30，evidence coverage 1.0，无 financial-advice phrase |
| 数据库迁移 | 通过 | schema v2；旧库升级、幂等、失败回滚、备份恢复 |
| 12 季度财务勾稽 | 通过 | AAPL 216、NVDA 214、XOM 168 个检查点 |
| scoped Ruff / diff check | 通过 | 当前变更无 lint 和 whitespace 错误 |

## 跳过项说明

- 1 个 browser integration：`agent-browser CLI not installed`。
- 3 个 transcript integration：需要显式 live flag 或 FMP key。
- 3 个 SEC integration：需要显式 live flag；本次另有 SEC reconciliation live 脚本通过。

## 发布阻塞项

1. Codex in-app Browser runtime 返回 `No browser is available`，尚无 1440/1024/390 三视口、键盘、console 和失败态截图证据。
2. Peer Group 后端、确认门和比较 API 已完成，但专用 Peer Analysis 前端及估值/预期/风险联合视图未完成。
3. 研究运行可以关联已有 FinRisk workflow；“从 Research Cycle 启动新 workflow”仍未接入。
4. 30 个 eval cases 共用 canonical demo fixture，证明 guardrail 和证据纪律，不应解释为 30 家公司的 live 数据验证。

## 发布决定

保持 roadmap 为“实施中”。浏览器真实验收、Peer UI 和新 workflow 启动完成后重跑本审计，再决定 tag。
