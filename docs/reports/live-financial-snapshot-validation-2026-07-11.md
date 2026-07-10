# SEC 财务快照 Live Validation

验证日期：2026-07-11  
数据源：SEC Company Facts API  
范围：AAPL、NVDA、XOM；公开数据只读验证。

## 结果

| Ticker | 当前 CIK | Revenue 单季数 | 重复 period end | TTM 数 | 最新单季与 TTM 对齐 | 告警数 |
|---|---|---:|---:|---:|---|---:|
| AAPL | 0000320193 | 60 | 0 | 21 | 2026-03-28 | 0 |
| NVDA | 0001045810 | 60 | 0 | 23 | 2026-04-26 | 0 |
| XOM | 0002115436 | 37 | 0 | 34 | 2026-03-31 | 2 |

三家公司均超过路线图要求的 12 个季度。latest TTM 与 latest quarter 对齐，且单季序列没有重复 period end。

## 本次 live smoke 发现并修复的问题

1. SEC 同一期可能同时提供 discrete frame 与 YTD 累计事实。原逻辑从 YTD 再推导一次单季，造成 period end 重复并破坏 TTM 窗口。现改为 reported discrete 优先，仅在缺少单季事实时派生。
2. SEC `fy` 会随比较申报重复出现，不能作为时间连续性的唯一依据。TTM、QoQ、YoY 改用实际 period-end 间隔校验；YTD 单季化使用共同 period start。
3. XOM 当前 ticker 对应新的 holding-company CIK，而历史经营事实仍位于 predecessor CIK 0000034088。系统现保留当前申报 CIK，并按显式审核的 continuity mapping 合并历史 companyfacts；不会依靠公司名称相似度自动推断前身关系。
4. 跨年份 XBRL concept 变化必须合并别名历史，不能在第一个命中 concept 后停止。

## 尚未证明的事项

- 本 smoke 证明序列连续性与数据形态，不等于逐项人工核对每个数值；
- XOM 的两个告警需按具体缺失指标继续确认；
- 银行、保险、外国发行人和 IFRS issuer 尚未覆盖；
- restatement 对历史点的选择策略仍需更多案例验证。

