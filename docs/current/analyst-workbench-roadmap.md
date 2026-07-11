# 分析师工作台能力路线图

状态：研究闭环首版已实现；当前执行转入[发布就绪与能力深化方案](release-readiness-roadmap.md)

更新日期：2026-07-11

目标：建设一个个人可持续使用、证据可追溯、能够跨季度复盘的公司研究与投资假设管理工具。

## 1. 产品原则

1. 事实、推断、用户假设和模型输出必须分层。
2. 财务、预期和观点都必须绑定 `as_of`，禁止时间穿越。
3. 未知值保持未知；不同币种、期间或行业口径不可比时显示 N/A。
4. LLM 可以解释和归类，不能在没有 before/after 证据时创建变化事实。
5. 系统生成研究队列，不生成自动买卖建议、仓位或不可解释的综合评分。

## 2. 当前能力总览

| 能力 | 当前状态 | 已实现 | 仍需补齐 |
| --- | --- | --- | --- |
| 研究结果交付 | 基本完成 | 完整风险报告、Claim–Evidence Matrix、Decision Ledger、研究就绪度 | 真实浏览器三视口与键盘验收 |
| 工程完整性 | 完成 | 模块 import smoke、API/workflow/monitor CLI、全量测试和构建 | 发布前安装与迁移演练 |
| 统一研究快照 | 完成 | point-in-time snapshot、manifest、source fingerprint、SQLite 历史、partial 状态 | 显式 schema version 与 migration runner |
| XBRL 财务标准化 | 基本完成 | FY/YTD/quarter/instant、Q4、TTM、同比/环比、margin、FCF、历史 CIK、IFRS/20-F/6-K | 12 季度逐项勾稽、公司配置、restatement、分部数据、银行 KPI |
| Transcript | 基本完成 | prepared/Q&A、guidance、topic、uncertainty、defensiveness、跨期比较及 live smoke | 默认研究运行自动接入、更多 provider 降级和 speaker/segment 精度 |
| 跨期变化 | 基本完成 | 财务、风险、guidance、管理层、证据覆盖；稳定 change ID；人工确认/忽略 | 来源冲突和过期、披露变化与真实事件变化、短语级措辞 diff |
| 风险财务映射 | 初版完成 | evidence-linked 定性传导通道与 Research Priority Score | 分部暴露、概率、金额、EPS/FCF 情景量化 |
| 市场预期 | 初版完成 | 手工录入、CSV、时间点历史、actual surprise、防财报后回填 | 外部 consensus provider、单位/口径映射和预期修订曲线 |
| 情景估值 | 初版完成 | Bull/Base/Bear、EV/Operating Income、隐含 margin、二维敏感性矩阵 | P/E、EV/EBITDA、FCF yield、简化 DCF 和行业模板 |
| Thesis 与复盘 | 基本完成 | Thesis、证伪条件、催化剂、Watchlist、复盘草稿、人工确认 | guidance 命中率、来源可靠度和个人判断校准 |
| 持续监控 | 初版完成 | 一次性 CLI、dry-run、并发、失败隔离、游标、去重提醒 | 请求节流、系统级定时配置、外部推送、政策/供应链事件触发 |
| 同行企业比较 | 初版完成 | 同 `as_of` 标准财务比较、不可比保护、研究队列、Watchlist UI | Peer Group、自动同行候选、币种转换、行业 KPI、估值和预期差横向表 |
| 质量验证 | 部分完成 | 后端 967 tests、前端 66 tests、30 个 guardrail cases、npm audit 0、SEC/IFRS 五公司勾稽、全新依赖安装 | 真实浏览器验收 |

## 3. 已形成的研究闭环

```text
FinRisk / SEC / Transcript
        ↓
point-in-time CompanyResearchSnapshot
        ↓
跨期 ResearchChange + 人工复核
        ↓
市场预期 + 情景估值 + Investment Thesis
        ↓
Watchlist 增量扫描 + 去重提醒
        ↓
财报后 PostEarningsReviewDraft
        ↓
人工确认并写回 Research Journal
```

该闭环已经可以手工或通过一次性 CLI 运行。尚未达到完全无人值守：默认风险接入、调度、外部推送和异常恢复仍需要生产化加固。

## 4. 当前阶段

### 阶段 A：研究闭环首版

状态：完成。

交付证据：

- [个人研究闭环补齐方案](research-closure-plan.md)
- [研究闭环真实数据验证](validation/research-closure-live-matrix-2026-07-11.md)
- [个人研究闭环使用指南](../guides/research-cycle.md)

### 阶段 B：发布就绪

状态：进行中。

核心任务：浏览器验收、12 季度勾稽、数据库迁移、30 个 golden cases、默认风险接入和恢复演练。

### 阶段 C：能力深化

状态：待实施。

核心任务：真正的同行企业分析、分部与行业 KPI、更多估值方法、外部预期、事件驱动监控和复盘校准。

## 5. 发布完成定义

`v0.1.0` 候选版本必须同时满足：

1. 在 1440、1024、390px 完成真实浏览器截图、键盘顺序和溢出检查。
2. AAPL、NVDA、XOM 各 12 个季度核心财务指标与来源勾稽。
3. 从现有数据库升级不会丢失 Thesis、Watchlist、快照、提醒或复盘。
4. 独立研究、关联 FinRisk、无 transcript 和 provider 失败均有明确结果或降级状态。
5. 至少 30 个 golden cases 覆盖行业、异常 filing、来源冲突和无重大变化。
6. 安装、首次研究、定时扫描、备份和恢复按文档从空环境演练通过。
7. 创建产品 tag 前单独确认版本号；历史实施 ID 不参与产品版本推算。
