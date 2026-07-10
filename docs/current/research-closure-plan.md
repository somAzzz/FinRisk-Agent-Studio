# 个人研究闭环补齐方案

状态：核心功能已实施并通过自动化、SEC 与 transcript live smoke；真实浏览器视觉验收和逐项财务人工勾稽待完成

制定日期：2026-07-11

目标发布：首个可重复安装和验证的个人研究闭环，候选版本 `v0.1.0`

基线：[分析师工作台路线图](analyst-workbench-roadmap.md)

## 1. 当前判断

项目已经具备财务快照、管理层信号比较、风险证据链、情景估值、Investment Thesis、Watchlist 和日期提醒，但这些能力仍是若干可手工调用的模块。当前最主要的缺口不是更多 Agent，而是把它们连接成可重复运行的研究周期：

```text
获取本期材料 → 固化时间点快照 → 与上期比较 → 判断重大变化
→ 更新估值和 Thesis → 生成提醒 → 财报后复盘
```

本方案完成前，不启动大规模多公司扫描，也不增加自动买卖建议或仓位功能。

## 2. 完成标准

满足以下条件后，个人研究闭环才算完成：

1. 对 Watchlist 公司执行一次命令或 API 调用，可以生成可复现的本期研究快照。
2. 每项变化同时保存 before/after、来源时间、证据 ID、检测规则和置信度。
3. 新 filing 或 transcript 到达时，只对相对上次快照的重大变化生成一次提醒。
4. 用户可以维护市场预期和 Bull/Base/Bear 假设，并查看敏感性矩阵与实际偏差。
5. 财报后能够生成“原 Thesis、原假设、实际结果、结论”的复盘草稿，由用户确认后写入 Journal。
6. AAPL、NVDA、XOM 加三类边界公司完成真实数据回归；核心路径在无外部 provider 时有明确降级状态。

## 3. 交付顺序

| 优先级 | 工作包 | 交付结果 | 依赖 |
| --- | --- | --- | --- |
| P0 | 统一研究快照与运行编排 | 现有能力进入同一次可追溯研究运行 | 无 |
| P0 | 跨期变化引擎 | 财务、风险、guidance、措辞变化使用统一契约 | 统一快照 |
| P1 | 市场预期与估值敏感性 | 实际值、用户预期和估值假设可比较 | 财务快照 |
| P1 | Watchlist 增量监控 | 一次扫描、去重提醒、失败隔离 | 快照与变化引擎 |
| P1 | 财报后复盘 | Thesis 与实际结果形成长期研究记忆 | 预期与监控 |
| P2 | 多公司比较 | 使用标准化事实横向比较，不做自动荐股 | 核心闭环通过验收 |
| P0 | 验证与候选发布 | 满足 `v0.1.0` 发布门槛 | 全部核心工作包 |

## 4. 工作包 A：统一研究快照与运行编排

### 4.1 数据契约

在 `src/research/models.py` 增加：

- `CompanyResearchSnapshot`：ticker、period、as_of、financials、management、risk observations、guidance、source manifest、warnings。
- `ResearchRunManifest`：run ID、输入来源、知识截止时间、组件状态、耗时和降级原因。
- `SnapshotComponentStatus`：`complete | partial | unavailable | failed`。

快照必须是 point-in-time；不得用知识截止日之后提交的 filing 或 transcript 回填历史结果。

### 4.2 编排与存储

建议新增：

```text
src/research/orchestrator.py
src/research/snapshot_store.py
tests/research/test_orchestrator.py
tests/research/test_snapshot_store.py
```

- 编排器调用现有 `FinancialResearchService`、`ManagementResearchService` 和风险报告适配器。
- SQLite 保存不可变快照、运行 manifest 和 source fingerprint。
- 相同 ticker、period、as_of、source fingerprint 的请求保持幂等。
- 单个 provider 失败时保留 partial snapshot，不把 fixture 静默当作 real 数据。
- 增加 `POST /research/runs`、`GET /research/runs/{run_id}` 和 ticker 快照历史查询。
- FinRisk 正常完成后可触发快照生成，但必须允许关闭，避免改变现有工作流语义。

### 4.3 验收

- 同一输入重复运行不产生不同快照。
- provider 缺失、超时、空 transcript、SEC 修订事实均有负面测试。
- API 返回各组件状态、数据截止时间和明确的 partial 原因。
- AAPL 至少连续两个季度可从同一入口生成快照。

## 5. 工作包 B：跨期变化引擎

### 5.1 统一变化模型

建议新增 `src/research/change_detection.py`：

```text
ResearchChange
  change_id
  ticker
  category: financial | risk | guidance | management | evidence
  status: new | persistent | strengthened | weakened | resolved
  materiality: low | medium | high | unknown
  before / after
  before_evidence_ids / after_evidence_ids
  detection_method
  confidence
  analyst_review_status
```

确定性规则优先，LLM 只能用于归类或解释，不能在没有 before/after 证据时创建变化事实。

### 5.2 检测范围

- 财务：同比、环比、TTM、利润率、FCF、债务及异常拐点。
- 风险：新增、增强、减弱、消失；区分披露变化和真实事件变化。
- Guidance：raise、cut、maintain、withdrawn、not comparable。
- 管理层：prepared remarks 与 Q&A 的语气差异、uncertainty、defensiveness 和主题迁移。
- 证据：来源冲突、证据撤回、来源过时和覆盖率下降。

### 5.3 接口与界面

- `GET /research/changes/{ticker}?from_snapshot=&to_snapshot=`。
- 前端按“重大变化 → 财务影响 → 原始证据”展示，默认隐藏无变化项。
- 每项变化提供“确认、忽略、需要复核”，结果写入 Journal，作为后续规则评估数据。

### 5.4 验收

- 每类至少包含新增、无变化、消失和冲突案例。
- 相同输入产生稳定的 change ID，重复扫描不会重复提醒。
- 所有 high materiality 变化具有 before/after 证据；否则自动降为 `unknown` 并要求复核。
- 两个连续季度的 transcript 可验证 guidance 和 Q&A 主题变化。

## 6. 工作包 C：市场预期与估值敏感性

### 6.1 预期数据

建议新增 `src/research/expectations.py`：

- 支持手工录入和 CSV 导入，外部 provider 放到后续适配层。
- 字段包含 ticker、metric、fiscal period、value、unit、source、observed_at、as_of、notes。
- 保存预期历史，不用最新值覆盖旧值；禁止拿财报后的修订预期计算 surprise。
- 支持 revenue、EPS、operating margin、FCF 和用户自定义 KPI。

### 6.2 估值增强

扩展 `src/research/valuation.py`：

- 增加增长率 × 利润率、利润率 × multiple 两类敏感性矩阵。
- 保留用户输入和 SEC 基线的来源区分。
- 增加 actual vs expectation 与 current price implied assumption。
- 不自动填入不可追溯的一致预期，不把模型输出写成 evidence claim。

### 6.3 验收

- CSV 重复导入幂等，列缺失、单位冲突、过期预期和财报后预期有明确错误。
- 敏感性矩阵单调性、边界值和负 equity value 有测试。
- 前端能够从实际值追溯至 SEC accession，从预期值追溯至用户或 provider 及其时间点。

## 7. 工作包 D：Watchlist 增量监控

### 7.1 执行模式

个人工具优先实现“一次性扫描命令”，由 cron、launchd 或 systemd timer 调度，不在第一版引入常驻分布式队列。

建议新增：

```text
src/research/monitor.py
src/research/alert_store.py
tests/research/test_monitor.py
tests/research/test_alert_store.py
```

- 逐公司隔离失败，单个 ticker 失败不终止整个 Watchlist。
- 保存上次成功游标、source fingerprint、snapshot ID 和扫描状态。
- 仅当 change ID 首次出现且达到用户 materiality 阈值时创建提醒。
- 提醒先持久化到应用内；邮件、Slack 等外部推送不是 `v0.1.0` 阻塞项。
- 提供 dry-run、单 ticker、最大并发和请求间隔配置。

### 7.2 验收

- 连续运行两次且来源未变时，第二次生成零条新提醒。
- SEC 限流、transcript provider 失败和单公司数据异常不丢失其他公司结果。
- 用户确认或忽略提醒后不会重复出现，除非证据或 materiality 发生变化。
- 日志不包含 API key、完整私有笔记或未脱敏 provider 响应。

## 8. 工作包 E：财报后复盘

- 从财报前最后一个 snapshot 锁定 Thesis、估值假设、预期和证伪条件。
- 新财报到达后生成 `PostEarningsReviewDraft`：预期 vs 实际、关键变化、催化剂结果、证伪条件状态和来源。
- 系统只能提出 `supported | mixed | invalidated` 建议，最终状态由用户确认。
- 用户确认后写入现有 `ResearchJournalStore`，保留原记录而不是覆盖。
- 累积 guidance 命中率、来源可靠度和用户判断校准数据，但样本不足时不展示伪精确评分。

验收：使用至少两个完整的前后期 fixture，证明旧假设不会被新数据回写，复盘结果可追溯到原始 snapshot。

## 9. 工作包 F：多公司比较（核心闭环后）

- 首版只比较同行公司标准化财务、变化类型、证据覆盖和用户定义 KPI。
- 所有公司必须使用相同 `as_of` 规则、货币与期间口径；不可比项显示 N/A。
- 候选扫描输出研究队列，不输出自动买卖建议或综合“神奇分数”。
- 该工作包不阻塞 `v0.1.0`，可作为下一次 minor release 的候选范围。

## 10. 测试与真实数据验证

### 自动化门禁

- 新模块单元测试、API contract tests、SQLite migration tests。
- point-in-time、幂等、去重、来源冲突、过期和 provider 降级测试。
- 前端空态、partial、needs-review、长列表与窄屏测试。
- 全量后端、前端测试及生产构建保持通过。

### Live matrix

| 类型 | 建议样本 | 重点 |
| --- | --- | --- |
| 大型科技 | AAPL、NVDA | 跨财年、快速增长、concept alias |
| 能源 | XOM | 历史 CIK、周期与现金流 |
| 银行 | JPM | 行业特有财务口径 |
| 生物科技 | MRNA | 收入波动、现金与研发 |
| 外国发行人 | TSM | 20-F/6-K、币种与期间差异 |

真实验证记录必须包含运行日期、source as-of、跳过项和人工核对结论，不只记录“请求成功”。

## 11. 实施节奏与退出门

建议按 6 个可独立合并的里程碑执行：

1. 统一快照契约、存储和 API。
2. FinRisk/financial/transcript 编排接入。
3. 跨期变化模型、规则与前端变化视图。
4. 预期存储、CSV、敏感性矩阵。
5. Watchlist 扫描、去重提醒和复盘草稿。
6. Live matrix、全量回归、迁移说明和候选发布检查。

每个里程碑必须满足：代码、测试、文档、失败降级和至少一个可演示路径同时完成。前一个里程碑的 schema 未稳定前，不并行扩展依赖它的 UI。

## 12. `v0.1.0` 候选发布门槛

- 核心完成标准 1–6 全部通过。
- 没有已知的数据穿越、重复提醒或 fixture 冒充真实数据问题。
- 数据库 schema 有迁移或兼容策略，升级不会静默丢失 Journal。
- 安装、配置、首次研究、定时扫描、备份与恢复均有用户指南。
- 真实数据矩阵完成并记录限制。
- 创建 tag 前单独确认版本号；历史实施 ID 不参与产品版本推算。
