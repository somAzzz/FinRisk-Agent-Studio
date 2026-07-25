# v0.1 财务勾稽记录

执行日期：2026-07-11

数据源：SEC Company Facts，包含 ticker resolver 返回的 current CIK 与 historical CIK。

复跑命令：

```bash
uv run python -m scripts.validate_financial_reconciliation
```

## 结果

| 公司 | 指标模板 | 通过指标 | N/A | 检查点 | 结论 |
| --- | --- | ---: | ---: | ---: | --- |
| AAPL | general | 11 | 0 | 216 | 通过 |
| NVDA | semiconductor | 11 | 0 | 214 | 通过 |
| XOM | energy | 9 | 2 | 168 | 通过，2 项有解释的 N/A |
| JPM | bank | 8 | 3 | 156 | 通过，银行口径缺失项明确 N/A |
| TSM | semiconductor | 11 | 0 | 88 | 通过，8 个 20-F 年度期间 |

每家公司检查最近 12 个可用期间。流量指标同时检查单季值与对应 TTM，时点指标检查最近 12 个时点。检查内容包括：

- reported 值与原始 SEC concept、accession、filed date、period end 和数值一致。
- Q2、Q3 的 YTD 差分和 Q4 的 `FY - Q3 YTD` 可从来源点重新计算。
- TTM 等于连续四个单季之和。
- FCF 等于同期间 CFO 减去 Capex 绝对值。
- 少于 12 个期间、来源不匹配或公式不一致均使命令返回非零状态。

## 已确认边界

- NVIDIA 近年 Capex 使用 `PaymentsToAcquireProductiveAssets`。该 alias 已进入 general 配置，恢复到最近 12 季度完整覆盖。
- Exxon Mobil 的 SEC Company Facts 没有稳定的标准 `GrossProfit` 与 `OperatingIncomeLoss` 概念。这两项明确记录为 N/A；Revenue、Net Income、CFO、Capex、FCF、现金、债务和稀释股数均通过 12 期间检查。
- N/A 只允许由验证矩阵显式声明。其他缺失一律判定失败，避免把 provider 或映射错误误报为“不适用”。
- JPM 使用 `RevenuesNetOfInterestExpense`、NII、credit-loss provision 与 deposits；标准 Company Facts 不提供稳定 CET1、Gross Profit 和 Operating Income，三项明确 N/A。
- TSM 的 SEC Company Facts 只有 8 个完整 20-F 年度期间，近期 6-K 单季事实并未持续进入该接口，因此按 8 个年度期间验证，不伪称 12 季度覆盖。
- 查询层支持 `original`、`amended_only` 和 `latest_known` restatement policy，且 `as_of` 仍禁止读取未来 amendment。

## 尚未覆盖

- 本记录验证标准化财务事实和派生公式，不替代页面显示、币种转换、同业口径和浏览器验收。
- SEC Company Facts 不包含维度化 segment axis；分部收入、分部利润与地域暴露仍需要 inline XBRL 或独立 provider，当前不会从合并口径推断。
