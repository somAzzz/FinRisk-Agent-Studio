# 分析师工作台优先级执行方案

状态：核心 P0–P2 首轮已完成；后续执行转入[个人研究闭环补齐方案](research-closure-plan.md)
制定日期：2026-07-11  
目标：把证据优先的风险工程原型补齐为个人可持续使用的季度公司研究与投资假设管理工具。

## 1. 执行原则

1. 先交付已有数据，再增加新 Agent。
2. 先建立跨期事实层，再生成趋势判断。
3. 财务影响、市场预期和估值必须与证据、假设和时间点绑定。
4. 未知值保持未知，不用伪精确分数掩盖数据缺口。
5. 每一阶段都必须有 fixture、单元测试、API contract 和至少一个真实 smoke case。

## 2. 优先级总表

| 优先级 | 工作包 | 目标结果 | 当前状态 |
|---|---|---|---|
| P0 | 研究结果前端交付 | 风险报告完整字段可见、claims 可追溯、研究就绪度可判断 | 本轮已实施，待全量验收 |
| P0 | 工程完整性门禁 | 所有正式模块可 import，断链入口被发现 | 已完成 import smoke 与根 CLI 正式入口 |
| P1 | 季度研究快照 | filing/transcript/XBRL 形成统一时间点快照 | XBRL 财务快照、API 与前端首版已实施 |
| P1 | 跨期变化检测 | 风险、措辞、guidance、财务指标可比 | 财务同比/环比/TTM 已实施；文本与 guidance 待实施 |
| P1 | 财务趋势与影响映射 | 风险连接到收入、利润率、EPS、FCF | 定性影响通道已实施；情景量化待实施 |
| P1 | Transcript 一等接入 | prepared remarks/Q&A 与历史季度对比 | 快照、比较工具/API/UI 已实施；自动随 workflow 运行待接入 |
| P2 | 市场预期与估值 | 手工/外部预期、情景估值、敏感性 | 用户假设情景引擎/API/UI 已实施；预期与敏感性矩阵待实施 |
| P2 | Thesis 与催化剂 | 假设、证伪条件、事件日期、状态 | SQLite journal、复盘 API 与 Research Journal UI 已实施 |
| P2 | Watchlist 与提醒 | 只推送相对上次研究的变化 | 持久化 API/UI 与 review/catalyst 到期提醒已实施；事件变化提醒待实施 |
| P3 | 多公司比较与扫描 | 行业横向比较和候选发现 | 待实施 |

## 3. Phase 0：已有价值交付与完整性（1 周）

### 3.1 前端报告补齐

任务：

- 渲染 `recent_changes`、`evidence_table`、`second_order_effects`；
- 渲染 evidence/inference/hypothesis 和置信度；
- 渲染 limitations、recommended questions；
- 将风险报告 claims 接入 Claim–Evidence Matrix；
- 增加 Analyst Decision Ledger；
- 去除用户可见的版本号术语。

验收：

- report contract fixture 的每类字段都有 DOM 断言；
- Claim Matrix 不再在有 claims 时显示空态；
- `npm test`、`npm run build` 通过；
- 实际浏览器完成 1440、1024、390 px 截图和键盘检查。

### 3.2 工程完整性门禁

任务：

- 新增 `tests/test_import_all_modules.py` 或等效 smoke；
- 核验 `discover_opportunities.py` 及其 schema；当前可导入，但 ticker 上下文尚未使用；
- 明确根 `main.py` 的正式用途或移除误导入口；已改为 API/workflow dispatcher；
- 给 CLI/API 的正式入口增加最小调用测试。

验收：`src` 下非可选模块全部可 import；不存在测试未覆盖的显式断链。

## 4. Phase 1：季度事实层（2–3 周）

### 4.1 统一季度快照模型

新增建议：

```text
src/research/models.py
src/research/snapshot_builder.py
src/research/store.py
```

核心模型：

- `CompanyResearchSnapshot`
- `FinancialPeriodSnapshot`
- `GuidanceSnapshot`
- `ManagementSignal`
- `RiskObservation`
- `SourceAsOf`

所有字段必须带 `as_of`、财年/季度、币种、单位、来源和 accession/URL。

### 4.2 XBRL 财务标准化

第一批指标：Revenue、Gross Profit、Operating Income、Net Income、CFO、Capex、FCF、Cash、Debt、Diluted Shares。

当前切片（2026-07-11）：已新增 `src/research` 标准模型与 builder，扩展 XBRL 期间/申报元数据，支持跨年份 concept aliases 合并、知识截止日期、重复事实选择、YTD 转单季、Q4 派生、TTM、同比/环比、利润率、总债务和可追溯 FCF 派生。`financial_snapshot_lookup` 已接入 company-research 工具目录，`GET /research/financials/{ticker}` 与前端 Financial Trend 已落地。尚未完成公司特有 concept 配置、12 季度真实三公司人工核对、分部财务和更完整的 restatement 策略。

处理要求：

- 去除 amendment 和重复 accession；
- 区分 FY、YTD、单季度和 instant facts；
- 处理公司 concept fallback；
- 保留原始 concept 与换算记录；
- 输出同比、环比、利润率和 TTM。

验收：AAPL、NVDA、XOM 各至少 12 个季度与年报数字对齐。

Live smoke（2026-07-11）：AAPL/NVDA/XOM 分别得到 60/60/37 个无重复 revenue 单季，最新 TTM 均与最新季度对齐。验证过程修复了 discrete+YTD 重复、错误依赖 SEC `fy` 以及 XOM 当前/历史 CIK continuity。详见 `docs/current/validation/sec-financial-snapshot-2026-07-11.md`。数值逐项人工核对仍待完成。

### 4.3 Transcript 结构化

- 区分 prepared remarks、Q&A、analyst question、management answer；
- 标记 CEO/CFO/其他管理层；
- 抽取 guidance、需求、价格、库存、margin、capex；
- 每个信号保留 quote、speaker、segment 和置信度。

当前切片（2026-07-11）：修复 sentiment pipeline 丢失 topic signals 的问题；新增管理层季度快照，保留 prepared remarks、Q&A、guidance、uncertainty、defensiveness、topic sentiment 与 evidence ids；新增跨期变化比较、`management_snapshot_lookup` Agent 工具、受鉴权 API 和前端季度选择/比较面板。尚待加入 FinRisk 自动固定流程和真实 provider 跨季度人工核对。

## 5. Phase 2：变化与影响（2–3 周）

### 5.1 跨期变化引擎

输出：

- 新增、持续、增强、减弱、消失的风险；
- 管理层关键措辞变化；
- guidance raise/cut/maintain；
- 分析师 Q&A 主题迁移；
- 财务指标异常与拐点。

禁止仅凭 embedding 相似度下结论；必须保留 before/after 引用和规则/模型解释。

### 5.2 风险财务映射

模型至少包含：

```text
risk_id
affected_segment
driver: volume | price | cost | margin | capex | working_capital
direction
time_horizon
bull/base/bear assumption
evidence_ids
confidence
```

将现有风险分数明确更名为 `ResearchPriorityScore`，新增独立维度：概率、财务影响、时间紧迫性、未定价程度。允许 `unknown`。

当前切片（2026-07-11）：前端已改称 Research Priority Score；结构化风险报告新增 evidence-linked financial impact channels，把风险映射到 volume、price、cost、margin、capex、working capital、financing 及对应财务指标。首版严格标记为 `unquantified`，概率与影响金额保持空值，待用户情景输入和分部暴露数据具备后再量化。

### 5.3 前端季度研究页

信息顺序：研究状态 → 本季变化 → 财务趋势 → guidance → 风险/机会 → 财务影响 → 证据 → 待验证问题 → 审计 trace。

## 6. Phase 3：估值与投资假设（2–3 周）

### 6.1 市场预期

先支持手工录入和 CSV 导入，再接外部 provider。记录来源时间，避免把旧预期与新财报比较。

### 6.2 情景估值

最低可用版本：

- Revenue growth、operating margin、tax、share count；
- Bull/Base/Bear 三情景；
- P/E、EV/EBITDA、FCF yield 或简化 DCF；
- 敏感性表；
- 当前价格隐含假设反推。

所有估值输出标记为用户假设，不进入 evidence claim。

当前切片（2026-07-11）：已实现严格要求 Bear/Base/Bull 三组显式输入的 EV/operating-income 情景引擎、受鉴权 API 和折叠式前端。只预填 SEC 可追溯的收入、净债务和股数；增长率、利润率、倍数及当前股价必须由用户输入。输出包含隐含每股价值、相对当前价格变化和当前价格隐含终端利润率，并明确不是预测或价格目标。敏感性矩阵与一致预期导入仍待实施。

### 6.3 Investment Thesis

字段：thesis、关键驱动、催化剂、证伪条件、关键监控指标、时间窗口、证据、状态、复盘结果。不输出自动买卖建议或仓位。

当前切片（2026-07-11）：已新增 typed Thesis、Catalyst、Review、Watchlist 模型及 SQLite journal；支持 thesis 筛选、证据关联、证伪条件、复盘后自动 invalidated、Watchlist upsert 和受鉴权 API。Research Journal 已作为前端一级入口，支持创建 thesis、强制填写证伪条件、加入 Watchlist 以及 supported/mixed/invalidated 复盘。自动变化提醒待实施。

Watchlist 已支持用户设置下一次复核日期，并把逾期/即将到期的 thesis review 与 catalyst 生成 Research Journal 待办。当前提醒是应用内、按日期确定性生成；尚未接入定时 worker、外部推送或基于新 filing/transcript 的事件触发。

## 7. Phase 4：持续监控与复盘（2 周）

- Watchlist 公司配置；
- 新 filing/transcript/政策/供应链事件检测；
- 只对相对上次快照的重大变化提醒；
- 催化剂日历；
- 财报后自动生成“原假设 vs 实际结果”；
- 记录管理层 guidance 命中率与来源可靠度。

## 8. 测试和质量门

每阶段统一要求：

- Pydantic/TypeScript contract fixture；
- 单元与属性边界测试；
- 缺失、冲突、过时数据负面案例；
- 至少一个 live smoke；
- 前端空态、失败、needs-review 测试；
- 不允许 fixture 在 real mode 静默冒充真实数据；
- 每个数值可回溯到原始事实与换算逻辑。

Golden cases 从 5 个扩展至至少 30 个，覆盖银行、生物科技、能源、外国发行人、小盘股、异常 filing 和无重大变化案例。

## 9. 完成定义

本路线图不是以“新增页面”完成，而是以下分析师任务可以闭环：

1. 选择一家公司，查看最新季度相对上季发生的变化；
2. 从变化定位到原始 filing/transcript/XBRL 证据；
3. 看见变化影响哪个财务变量；
4. 更新情景与投资假设；
5. 记录证伪条件和催化剂；
6. 下一季度自动比较并完成复盘。
