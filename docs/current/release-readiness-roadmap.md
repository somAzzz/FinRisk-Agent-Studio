# 发布就绪与能力深化方案

状态：实施中

制定日期：2026-07-11

目标：在不推翻现有研究闭环的前提下，补齐 `v0.1.0` 发布阻塞项，并把基础 Watchlist 比较升级为真正可用的同行企业分析。

基线：

- [分析师工作台能力路线图](analyst-workbench-roadmap.md)
- [个人研究闭环补齐方案](research-closure-plan.md)
- [研究闭环真实数据验证](validation/research-closure-live-matrix-2026-07-11.md)
- [12 季度财务勾稽记录](validation/financial-reconciliation-2026-07-11.md)
- [候选发布审计](validation/release-audit-2026-07-11.md)

## 0. 当前执行状态

| 工作包 | 状态 | 已完成 | 剩余退出条件 |
| --- | --- | --- | --- |
| 浏览器与可访问性 | 阻塞 | 前后端自动化与生产构建已有基线 | Browser runtime 恢复、三视口与键盘真实验收 |
| 数据库迁移与恢复 | 完成 | 事务迁移、幂等、失败回滚、在线备份/恢复、CLI 和测试 | 纳入最终发布审计 |
| 财务正确性与行业事实 | 进行中 | AAPL/NVDA/XOM 12 期间勾稽；六类指标配置 | JPM、TSM、restatement 与分部事实 |
| 默认编排与变化可信度 | 进行中 | 组件状态语义、correlation ID、风险来源 manifest、来源冲突/过期规则 | 启动新 FinRisk run、Watchlist 组件策略、guidance 数值与措辞 diff |
| 同行企业分析 | 进行中 | 持久化 Peer Group、确认门、行业/币种/财年策略、快照新鲜度比较 API | 候选生成、估值/预期/风险联合视图和专用前端区域 |
| 估值与监控深化 | 进行中 | P/E、EV/EBITDA、FCF yield、简化 DCF；扫描节流与重试参数 | assumptions 历史、系统定时器模板、事件级 cursor 和可选推送 |
| Golden cases 与发布审计 | 进行中 | 30/30 guardrail cases、后端 962 tests、前端 64 tests、生产构建 | 全新安装、真实浏览器和最终发布门禁 |

## 1. 范围判断

现阶段不再增加新的通用 Agent。工作的重点从“功能存在”转为三类结果：

1. **可信**：财务期间、数据库升级、来源冲突和浏览器交付经过真实验收。
2. **可持续**：风险、transcript、提醒和复盘可以稳定进入同一研究周期。
3. **可比较**：同行公司在相同时间、期间、币种和行业 KPI 下进行横向分析。

## 2. 优先级

| 优先级 | 工作包 | 结果 | 是否阻塞 `v0.1.0` |
| --- | --- | --- | --- |
| P0 | 浏览器与可访问性验收 | 三视口、键盘、溢出和失败态真实通过 | 是 |
| P0 | 数据库迁移与恢复 | 旧数据库安全升级，可备份和恢复 | 是 |
| P0 | 12 季度财务勾稽 | AAPL、NVDA、XOM 核心指标逐期匹配 | 是 |
| P0 | 默认研究编排闭环 | FinRisk、SEC、transcript 自动进入同一快照 | 是 |
| P0 | Golden cases 扩充 | 至少 30 个跨行业和负面案例 | 是 |
| P1 | 变化检测深化 | 冲突、过期、措辞和事件语义更可靠 | 否 |
| P1 | 同行企业分析 | Peer Group、行业 KPI、估值与预期横向比较 | 否 |
| P1 | 估值方法扩展 | P/E、EV/EBITDA、FCF yield、简化 DCF | 否 |
| P1 | 本地调度与节流 | 可配置请求间隔、失败重试和系统定时任务 | 否 |
| P2 | 外部预期与推送 | consensus provider、邮件或移动端提醒 | 否 |
| P2 | 判断校准 | guidance、来源和 Thesis 历史准确度 | 否 |

## 3. 工作包 A：浏览器与可访问性验收

### 3.1 环境恢复

当前阻塞发生在 Codex 浏览器运行时发现阶段，返回 `No browser is available`，不是 Vite 或后端启动失败。优先处理：

1. 更新并重启 ChatGPT/Codex 桌面应用。
2. 确认内置 Browser capability 可用，清理插件版本不一致问题。
3. 重新连接本地 `http://127.0.0.1:5173`。
4. 只有明确选择 Chrome 控制时才安装 Chrome 和对应连接扩展；单独安装 Chrome 不视为完成。

### 3.2 验收矩阵

| 视口 | 重点 |
| --- | --- |
| 1440px | 信息层级、大表格、Research Cycle 与审计区 |
| 1024px | 侧栏和主区竞争、同行比较、敏感性矩阵 |
| 390px | 表格横向滚动、按钮换行、输入表单、固定元素遮挡 |

每个视口检查：

- 首次空态、加载、partial、failed、needs-review 和长列表。
- Tab 顺序、焦点可见性、Enter/Space 操作和表单 label。
- `prefers-reduced-motion`、颜色对比度和状态不只依赖颜色。
- 浏览器 console 无错误，网络失败给出可行动提示。

验收产物：三视口截图、问题清单、修复提交和浏览器 smoke 记录。

## 4. 工作包 B：数据库迁移与恢复

### 4.1 迁移框架

已实现：

```text
src/research/database.py
tests/research/test_database_migrations.py
```

要求：

- 使用 `PRAGMA user_version` 或独立 schema metadata 记录版本。
- 所有迁移在事务中执行，失败时完整回滚。
- 每次升级前检查数据库完整性并记录备份路径。
- 禁止通过删除表完成升级；JSON payload 变更必须提供兼容读取或数据迁移。
- Snapshot 与 Journal 分库和同库两种配置都要通过。

### 4.2 验收

- 从当前数据库 fixture 升级后，Thesis、Watchlist、快照、提醒和复盘数量不变。
- 重复运行迁移幂等。
- 中途失败不会留下半升级 schema。
- 备份 → 写入新数据 → 恢复 → 只读核验流程通过。

## 5. 工作包 C：财务正确性与行业事实层

### 5.1 12 季度勾稽

对 AAPL、NVDA、XOM 至少核对：

- Revenue、Gross Profit、Operating Income、Net Income。
- CFO、Capex、FCF。
- Cash、Current Debt、Long-term Debt、Diluted Shares。
- Q1、YTD 转单季、Q4 派生、TTM 和 restatement。

每个值保存：标准化值、原 concept、accession、filed date、期间、换算公式和人工结论。

### 5.2 公司与行业配置

已新增可审计配置，新的 alias 不再继续硬编码在 builder：

```text
config/financial_metrics/general.json
config/financial_metrics/bank.json
config/financial_metrics/saas.json
config/financial_metrics/energy.json
config/financial_metrics/semiconductor.json
config/financial_metrics/biotech.json
```

首批行业 KPI：

| 行业 | KPI |
| --- | --- |
| 银行 | NII、NIM、provision、CET1、贷款和存款增长 |
| SaaS | ARR、NRR、RPO、SBC、FCF margin |
| 半导体 | inventory days、capex intensity、utilization、gross margin |
| 能源 | production、realized price、unit cost、reserve replacement |
| 生物科技 | cash runway、R&D、milestone、trial phase |

### 5.3 Restatement 与分部

- 保留 original、amended 和 latest-known 三种查询语义。
- 同一 `as_of` 不得使用未来 amendment。
- 增加 segment revenue、segment profit 和 geographic exposure；无法稳定映射时保持 raw label。

验收：三家公司 12 季度核心指标全部通过；JPM 与 TSM 至少各完成一套行业/外国发行人负面案例。

## 6. 工作包 D：默认研究编排与变化可信度

### 6.1 默认闭环

当前风险适配支持 `workflow_run_id`，自动快照通过 `RESEARCH_SNAPSHOT_ON_WORKFLOW=1` 启用。下一步：

- Research Cycle 可以选择已有 FinRisk run，或明确启动新 run。
- Watchlist 配置每家公司需要的组件：financial、transcript、risk、supply chain。
- 组件未请求使用 `not_requested`，provider 缺失使用 `unavailable`，执行失败使用 `failed`，避免所有独立扫描都显示含糊的 partial。
- workflow、snapshot、change 和 alert 共享 correlation ID。
- 自动触发保持可关闭，且展示预计请求量和数据源。

### 6.2 变化检测深化

新增：

- `source_conflict`：同一事实跨来源值或方向冲突。
- `source_stale`：来源超过用户阈值。
- `disclosure_change` 与 `observed_event_change` 分离。
- guidance 的 numerical range、midpoint、单位和期间比较。
- 管理层措辞 before/after quote diff，LLM 解释必须引用两侧证据。
- ignored/confirmed/needs-review 反馈统计，用于规则评估，不直接训练模型。

验收：每类变化包含新增、无变化、增强、减弱、消失、冲突和 provider 缺失案例；provider 缺失不得生成“风险已消失”。

## 7. 工作包 E：同行企业分析

当前的 Compare Watchlist 是事实层第一版。目标是升级为可保存、可解释、行业感知的 Peer Analysis。

### 7.1 Peer Group 模型

建议新增：

```text
PeerGroup
  peer_group_id
  name
  base_ticker
  members
  industry_template
  currency_policy
  fiscal_period_policy
  user_notes
  created_at / updated_at

PeerMember
  ticker
  inclusion_reason
  source
  confirmed_by_user
```

- 用户可以手工建立同行组。
- 系统可以根据 SIC、业务描述、收入结构和供应链关系提出候选，但必须由用户确认。
- 自动候选必须展示 inclusion reason，不把行业标签相同当作业务可比的充分条件。

### 7.2 标准化层

- 统一 `as_of`，并显示各公司信息新鲜度差异。
- 财年错位时支持 latest-quarter、calendarized TTM 和 latest-FY 三种视图。
- 币种策略：原币、指定展示币种、禁止换算；汇率必须有 source 和 as-of。
- 会计口径或行业 KPI 不可比时显示 N/A 和原因。
- reported、derived、user-entered、provider 四类 lineage 必须可见。

### 7.3 分析视图

最小交付：

1. 财务趋势：增长、margin、FCF、capital intensity、debt。
2. 估值：P/E、EV/EBITDA、FCF yield 和用户选择的行业 multiple。
3. 预期差：actual surprise、预期修订方向和数据时间。
4. 风险变化：新增/增强/减弱及证据覆盖。
5. 行业 KPI：由 Peer Group 模板决定。
6. 历史分位：公司相对自身历史与同行中位数，禁止合并为单一神奇分数。

### 7.4 API 与前端

建议：

```text
POST /research/peer-groups
GET  /research/peer-groups
GET  /research/peer-groups/{id}/comparison
POST /research/peer-groups/{id}/candidates
```

前端增加 Peer Analysis 一级区域：同行组管理、口径控制、指标选择、缺失说明和证据抽屉。

验收：至少为大型科技、半导体、能源、银行各建立一组 fixture；跨币种、财年错位、缺失 KPI 和同行候选拒绝均有测试。

## 8. 工作包 F：估值与市场预期深化

### 8.1 估值方法

- P/E：明确 forward/trailing EPS、稀释股数和负盈利不可用状态。
- EV/EBITDA：展示 EV、净债务、EBITDA 来源与租赁处理。
- FCF yield：区分 equity FCF 与 enterprise FCF。
- 简化 DCF：显式预测期、WACC、terminal growth、净债务和 share count。
- 所有方法共享敏感性引擎，并保存用户 assumptions snapshot。

### 8.2 预期

- 先定义 provider-neutral consensus contract，再接外部数据源。
- 保存每次修订，不覆盖历史；比较 7/30/90 天 revision。
- provider 数据与用户预期并列，不自动覆盖用户模型。
- 预期值的币种、GAAP/non-GAAP、财年和更新时间必须明确。

验收：负 EPS、负 EBITDA、负 equity value、币种冲突、过期 consensus 和财报后修订均有明确结果。

## 9. 工作包 G：监控、复盘和判断校准

### 9.1 本地生产化

- `MonitorScanRequest` 增加请求间隔、每 provider 并发、重试和超时。
- 提供 launchd、cron、systemd timer 示例及健康检查。
- 扫描摘要记录成功、unchanged、partial、failed 和下一次建议操作。
- 外部推送为 adapter；第一批可选 email/webhook，不保存明文凭证。

### 9.2 事件触发

- 新 filing、transcript、政策和供应链事件分别维护 cursor。
- 同一事实跨来源只生成一个 alert，并保留来源列表。
- materiality 规则由用户按公司或 Peer Group 配置。

### 9.3 校准

在样本充分后计算：

- guidance range 命中率和偏差。
- 来源支持/冲突/撤回次数。
- Thesis supported/mixed/invalidated 历史。
- 用户确认和忽略变化的比例。

少于预设最小样本时只展示原始计数，不显示百分比评分。

## 10. 工作包 H：Golden cases 与发布验收

### 10.1 30 个 Golden cases

| 类别 | 最少数量 |
| --- | ---: |
| 大型科技与正常 filing | 5 |
| 银行和行业专用 KPI | 4 |
| 能源与周期变化 | 4 |
| 生物科技与缺失收入 | 3 |
| 外国发行人、20-F、6-K、币种 | 4 |
| amendment、restatement、历史 CIK | 3 |
| transcript 缺失、冲突或 guidance withdrawn | 3 |
| 无重大变化和重复扫描 | 2 |
| 安全边界与 fixture 泄漏 | 2 |

每个 case 固定输入、知识截止时间、预期变化、禁止行为和证据要求。

### 10.2 发布门禁

- 后端全量测试、前端测试、TypeScript 和生产构建通过。
- scoped Ruff、Markdown 链接和 `git diff --check` 通过。
- 真实浏览器验收通过。
- 数据库升级、备份、恢复通过。
- 12 季度勾稽和 live matrix 通过并记录限制。
- 从全新环境按用户指南完成首次研究与一次定时扫描。
- 没有已知时间穿越、重复提醒、错误币种比较或 fixture 冒充真实数据。

## 11. 推荐实施顺序

### Sprint 1：发布基础

浏览器验收、数据库 migration runner、恢复测试。

退出门：旧数据库无损升级，三视口通过。

### Sprint 2：财务可信度

12 季度勾稽、公司配置、restatement、银行/外国发行人负面案例。

退出门：AAPL、NVDA、XOM 核心指标通过，JPM/TSM 边界明确。

### Sprint 3：默认闭环与变化质量

风险和 transcript 默认编排、组件状态语义、冲突/过期/措辞变化。

退出门：完整、partial、failed、not-requested 路径均可解释。

### Sprint 4：Peer Analysis

Peer Group、标准化层、同行财务/估值/预期/风险视图。

退出门：四类行业同行组 fixture 与前端验收通过。

### Sprint 5：估值与监控深化

更多估值方法、本地 scheduler 配置、请求节流、事件 cursor 和可选推送。

退出门：无人值守扫描一周无重复提醒和静默失败。

### Sprint 6：Golden cases 与候选发布

扩充到 30 cases，执行全量回归、安装、备份恢复和发布审计。

退出门：所有 `v0.1.0` 门禁通过后，再由用户确认是否创建 tag。

## 12. 非目标

- 不实现自动买卖建议、仓位和交易执行。
- 不把 Peer Analysis 合并为不可解释的单一评分。
- 不为了“自动化”在 provider 失败时使用 fixture 代替真实数据。
- 不在没有分部暴露和用户假设时输出伪精确财务影响金额。
