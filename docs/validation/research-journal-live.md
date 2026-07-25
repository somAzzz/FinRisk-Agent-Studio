# v0.1 Research Journal 本地 LLM 全链路验收

日期：2026-07-12  
场景：AAPL 2024FY → 2025FY，peer MSFT 2025FY  
运行指南：[Research Journal 本地 LLM 真实验收](../testing/research-journal-live-acceptance.md)

## 结果

隔离场景在真实 Chromium 和本地 vLLM 上通过，耗时 46.6 秒。workflow `run-e47b2732703c` 以非 demo、非 cached 模式运行，模型为 `nvidia/Qwen3.6-27B-NVFP4`，服务报告 `max_model_len=262144`；LLM log 有 7 次成功调用。

| 验收项 | 证据 | 结果 |
| --- | --- | --- |
| Thesis / Watchlist | 1 个 active thesis、1 个 Watchlist item | 通过 |
| 跨期研究 | AAPL 2 个真实快照、变化人工 Confirm | 通过 |
| 本地 LLM 联动 | vLLM payload 与 log 双重校验 | 7 次成功 |
| Expectation–Actual | 2025FY 历史 expectation 与实际值比较 | 通过 |
| 估值 | scenario、sensitivity、multiple、DCF 均写入 history | 4/4 |
| Peer Analysis | AAPL/MSFT，6 行财务比较 | 通过 |
| 财报后复盘 | draft 生成为 confirmed/supported | 通过 |
| 浏览器质量 | console/HTTP error 为空，390px 无横向溢出 | 通过 |

本地证据目录：

```text
artifacts/research-journal-live/aapl-msft-quarterly-review-20260712T102338Z/
```

目录含结构化 `report.json`、浏览器报告、两份隔离 SQLite、服务日志及桌面/移动端截图。`artifacts/` 被 gitignore，仅保留在执行机器，不提交运行数据。

## 实跑发现并修复的问题

1. Research Cycle 未向 FinRisk workflow 传递 LLM 选择，后端会回落到默认 provider；现已传递完整 `llm_config`。
2. Expectation 表单只能用当天时间，无法合法录入历史财报前预期；现已增加 observed/as-of 日期并校验顺序。
3. 新建 thesis 后 Reviews 子面板保留旧列表，导致 Generate draft 禁用；现已通过 journal revision 同步全局研究数据。
4. Vite proxy 固定指向 8000，无法安全运行隔离验收；现支持 `FINRISK_API_PROXY_TARGET`。
