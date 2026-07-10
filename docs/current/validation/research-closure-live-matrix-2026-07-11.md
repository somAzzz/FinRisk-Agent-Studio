# 研究闭环真实数据验证

验证日期：2026-07-11

范围：SEC Company Facts、统一财务快照、IFRS/20-F 边界、Watchlist 重复扫描去重。所有请求均为公开数据只读访问。

## 公司矩阵

| 类型 | 公司 | 结果 | 结构化指标 | 变化记录 | 警告 |
| --- | --- | --- | ---: | ---: | ---: |
| 大型科技 | AAPL | 通过 | 1932 | 1522 | 0 |
| 大型科技 | NVDA | 通过 | 1782 | 1384 | 0 |
| 能源 | XOM | 通过，存在缺失项 | 1060 | 1021 | 2 |
| 银行 | JPM | 通过，行业口径有限 | 760 | 715 | 3 |
| 生物科技 | MRNA | 通过，部分指标缺失 | 776 | 737 | 2 |
| 外国发行人 | TSM | 通过，当前 SEC facts 以年报为主 | 133 | 79 | 0 |

TSM 初次验证得到零指标，原因是构建器仅接受 US-GAAP aliases 和 10-K/10-Q。修复后已支持 IFRS aliases、20-F 年报和按持续时间识别的 6-K quarter/YTD。当前 TSM 快照得到 90 个 annual points；SEC Company Facts 中没有可供当前路径使用的近期离散季度，因此不能声称季度覆盖已经完成。

## 最新年收入 lineage 勾稽

逐家公司将标准化快照的最新 annual revenue，按 `source_concept + accession + period_end + value` 回查 SEC 原始 Company Facts；六家公司全部精确匹配：

| 公司 | 期间 | 标准化值 | Concept | Accession | 结果 |
| --- | --- | ---: | --- | --- | --- |
| AAPL | 2025-09-27 | USD 416,161,000,000 | RevenueFromContractWithCustomerExcludingAssessedTax | 0000320193-25-000079 | MATCH |
| NVDA | 2026-01-25 | USD 215,938,000,000 | Revenues | 0001045810-26-000021 | MATCH |
| XOM | 2025-12-31 | USD 332,238,000,000 | Revenues | 0000034088-26-000045 | MATCH |
| JPM | 2025-12-31 | USD 182,447,000,000 | Revenues | 0001628280-26-008131 | MATCH |
| MRNA | 2025-12-31 | USD 1,944,000,000 | RevenueFromContractWithCustomerExcludingAssessedTax | 0001682852-26-000033 | MATCH |
| TSM | 2024-12-31 | USD 88,268,000,000 | Revenue | 0001193125-25-083423 | MATCH |

XOM 使用当前与历史 CIK continuity，回查同时覆盖 `historical_ciks`，避免只查询当前 registrant CIK 得出错误的 MISMATCH。

## Watchlist 去重

使用隔离的临时 SQLite 数据库连续扫描 AAPL 两次：

```text
first  partial   snapshot-12756e9684b44b0f  changes=0 alerts=0
second unchanged snapshot-12756e9684b44b0f  changes=0 alerts=0
persisted snapshots=1
cursor=snapshot-12756e9684b44b0f
```

首次为 `partial`，因为当前 CLI 默认没有 risk report adapter，且未请求 transcript period；SEC 财务组件成功。第二次来源未变化，没有新增快照或提醒，cursor 继续指向已持久化快照。

## Transcript matrix

使用 DefeatBeta 真实 provider 比较 2025Q2 与 2025Q1：

| 公司 | 当前/对比 transcript | 变化 | 当前证据 ID |
| --- | --- | ---: | ---: |
| AAPL | 成功 / 成功 | 4 | 86 |
| NVDA | 成功 / 成功 | 1 | 34 |
| XOM | 成功 / 成功 | 0 | 46 |

三家公司均完成 prepared remarks、Q&A、guidance 与 topic signal 的解析和跨期比较。零变化表示当前确定性规则没有发现达到阈值的信号，不代表没有业务变化。

## 验证边界

- 本次验证证明公开 SEC 数据路径、单次 transcript 跨期比较和来源未变化去重，不证明 transcript provider 的长期稳定性。
- 已完成六家公司最新 annual revenue 的原始 Company Facts 精确勾稽；其他指标与历史季度尚未逐项人工核对。
- JPM 的银行专用 KPI、TSM 的币种转换与近期 6-K 季度覆盖仍应扩充。
- 浏览器运行时在本次环境中没有可用实例；前端通过 62 项组件测试和 TypeScript/Vite 生产构建，但真实浏览器视觉验收仍待补充。
