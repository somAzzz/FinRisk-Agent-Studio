# FinRisk Agent Studio 产品前端架构

## 产品定义

FinRisk Agent Studio 是面向个人金融分析师的 evidence-first 研究工作台。前端不再以“调用哪个 Agent”作为主导航，而以分析师的连续工作为核心：发现变化、理解公司、复核证据、维护 Thesis。

## 页面地图

```text
Today
├── Needs review
├── Recent activity
└── Start research

Companies
└── /AAPL
    ├── Overview
    ├── Risks
    ├── Financials
    ├── Valuation
    ├── Management
    ├── Supply Chain
    └── Evidence

Research Runs
├── Run history
├── Agent run
├── Tool trace
├── Evidence candidates
└── Human review

Journal
├── Research cycle
├── Thesis ledger
├── Watchlist
├── Expectations
├── Peer analysis
└── Post-earnings review
```

## 各页面的单一职责

### Today

回答“今天最需要处理什么”。只显示需要人工复核的变化、最近运行和下一次计划任务。运行器是次级动作，不占据首屏主体。

### Company Overview

回答“这家公司的最新风险位置是什么”。固定顺序为 Decision brief → Top risks → Evidence confidence → Technical trace。技术执行过程默认折叠。

### Company 子页面

- Risks：完整风险报告、影响渠道和变化。
- Financials：SEC 标准化事实、变化和 lineage。
- Valuation：显式假设与情景，不与事实混在一起。
- Management：财报电话会主题和口径变化。
- Supply Chain：产品依赖图和节点证据。
- Evidence：Claim grounding、质量门禁、证据矩阵和图路径。

### Research Runs

面向高级分析和审计。保留 planner、tools、rounds、trace、candidate、review 等技术密度，但不让这些概念占据普通用户的主页面。

### Journal

管理跨时间的研究记忆。Thesis、反证条件、Expectations、Watchlist 和财报后复盘在同一产品域中，但通过任务导航分层。

## 路由约定

使用静态托管兼容的 hash route：

- `#/today`
- `#/companies/AAPL/overview`
- `#/companies/AAPL/risks`
- `#/companies/AAPL/financials`
- `#/companies/AAPL/valuation`
- `#/companies/AAPL/management`
- `#/companies/AAPL/supply-chain`
- `#/companies/AAPL/evidence`
- `#/runs`
- `#/journal`

## 视觉系统

- Graphite `#111820`：全局导航和产品身份。
- Canvas `#F7F9FB`：长时间阅读背景。
- Ink `#17202A`：正文与关键数字。
- Evidence teal `#1F7A7A`：证据、可信度、选中状态。
- Review amber `#B7791F`：人工复核。
- Failure red `#C2413D`：失败、冲突和不可用。

等宽字体只用于 ticker、run ID、时间戳和 evidence ID。正文与操作使用 humanist sans。保留 evidence rail 作为产品签名，但取消全局网格背景、重复 NODE 标签和永久悬浮监视器。

## 交互原则

1. 结果优先于执行过程。
2. 运行前解释问题和证据范围；模型设置默认折叠。
3. 系统健康状态必须来源于真实检查，未知即显示未知。
4. 每个禁用动作需要可理解的前置条件。
5. Activity 是按需 Drawer，不覆盖主任务。
6. 390px 下不允许 fixed 控件遮挡正文或 CTA。
