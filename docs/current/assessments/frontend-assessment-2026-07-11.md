# FinRisk Agent Studio 前端评估报告

评估日期：2026-07-11  
评估视角：个人金融分析师  
评估证据：`frontend/src` 源码、组件测试、API 类型、静态 demo fixtures、构建配置和现有 E2E 脚本。

## 1. 验证边界

评估期间尝试连接应用内浏览器，对本地 `127.0.0.1:5173` 做真实渲染和交互检查，但当前会话没有可用浏览器实例。因此本报告不声称完成像素级、真实键盘导航或多视口截图验收。结论主要来自源码、测试与构建证据；真实视觉 QA 被列为待补验收项。

## 2. 总体结论

当前前端是一套功能覆盖较完整的 Agent 工程控制台，而不是成熟的分析师研究终端。它擅长展示“系统做了什么”，但此前没有优先回答分析师最关心的三个问题：

1. 研究是否已经达到可用状态？
2. 与上次相比发生了什么变化？
3. 哪些结论仍需验证，下一步查什么？

整改前评分：**6.2 / 10**。完成 P0 数据展示、Financial Trend、风险财务影响通道、评分语义和 Research Journal 后，源码与测试口径复评分为 **7.7 / 10**；仍需真实浏览器验收后确认。

最终自动化验收：16 个前端测试文件、60 个测试全部通过，TypeScript build 与 Vite production build 通过。应用内浏览器实例仍不可用，因此不把自动化 DOM 测试等同于真实视觉与键盘验收。

## 3. 信息架构

现有一级视图分为 Risk Intelligence、Product Supply Chain 和 LLM Agent Runs，另有固定 Run History 和 Process Monitor。这种划分符合工程模块，但不完全符合分析师心智模型。

优点：

- 主功能边界清楚；
- run history 能在不同工作流之间切换；
- trace、evaluation、graph、report 均有明确入口；
- 静态 demo 能在无后端环境展示核心能力。

问题：

- 风险页把 Timeline、两套 Evaluation、Report、Score、Claim Matrix、Graph 顺序堆叠，首屏认知负担较大；
- “运行状态”和“研究结论”没有足够清晰地分层；
- 对个人分析师而言，Agent Runs 是调试工具，不应与公司研究和供应链研究拥有同等导航权重；
- 缺少公司 dossier、季度对比、财务趋势、估值和 thesis 页面。

建议未来一级导航改为：公司研究、供应链、Watchlist；Agent Trace 和系统评估下沉到“审计与运行详情”。

## 4. 核心页面评估

### Risk Intelligence

优点：Workflow launcher 参数较完整；报告、评分、图和质量信息均已组件化；静态 demo 便于演示。

整改前关键缺陷：

- `report_v16` 的近期变化、证据表、二阶影响、事实/推断、局限性和后续问题未展示；
- Claim–Evidence Matrix 被固定传入空数组；
- 用户需要穿过 Timeline 和 Evaluation 才能看到研究结论；
- 内部阶段编号曾暴露在界面，不符合最终用户语言；
- 风险分数未明确是研究优先级，而非发生概率或预期损失。

本轮已补：完整风险报告展示、Claim Matrix 数据绑定、顶部 Analyst Decision Ledger。

### Product Supply Chain

优点：探索、展开、节点详情、Sankey、质量 verdict 和 fallback 信息覆盖较完整。

问题：

- 供应链边的证据强弱与新鲜度需要更直接地体现在图上；
- 缺少按产品、收入分部、地区和关键材料筛选；
- 缺少“这条关系影响哪个财务变量”的映射；
- Sankey 适合展示流向，但不天然表示持股风险或经济暴露，应避免用户误读宽度含义。

### LLM Agent Runs

优点：tool events、预算、证据候选、review action、fallback 均可观察，适合开发与审计。

问题：

- 信息密度较高，业务用户容易被工具实现细节淹没；
- 应默认折叠原始 trace，先展示研究产出、失败原因和需人工处理事项；
- provider/base URL/tool loop 等配置更适合放在高级设置。

## 5. 视觉与交互

现有视觉采用白色卡片、slate 文本、emerald 强调色，清晰、克制，符合内部工具。缺点是大量卡片的视觉权重近似，无法快速区分“决策信息、质量警告、系统日志”。

本轮新增的 Analyst Decision Ledger 作为唯一视觉焦点，使用深蓝墨色和青绿色台账边线，集中展示研究状态、最高风险、证据来源、claim 覆盖率、近期变化和下一步尽调。其余界面保持安静，以避免全面重做造成风格割裂。

仍需改进：

- 系统性清理 inline style，建立表格、数据标签、状态和空态 token；
- 为所有 button/link/input 增加一致的 `:focus-visible`；
- 检查窄屏下固定侧栏、底部 history/process monitor 的空间竞争；
- 为大表格和图提供明确的横向滚动或全屏模式；
- 遵守 `prefers-reduced-motion`，并完成实际键盘顺序测试。

## 6. 前端模块评分

| 模块 | 整改前 | 本轮后 | 说明 |
|---|---:|---:|---|
| 功能覆盖 | 8.0 | 8.4 | 三类工作流均有 UI，补齐结构化报告数据展示 |
| 分析师信息架构 | 5.0 | 6.5 | 新增决策摘要，但仍以工程模块为主 |
| 研究结论表达 | 5.5 | 7.5 | 已展示变化、证据、二阶影响、限制和问题 |
| 证据可追溯性 | 7.0 | 8.2 | Claim Matrix 接入真实报告 claims |
| 状态与错误反馈 | 7.5 | 7.5 | trace/fallback 较完整，错误恢复指导仍有限 |
| 视觉层级 | 6.0 | 7.0 | 新增单一研究台账焦点 |
| 响应式 | 6.0 | 6.4 | 新组件有断点，完整页面仍需多视口实测 |
| 无障碍 | 5.0 | 5.0 | 有 aria 基础，缺完整键盘与对比度验收 |
| 自动化测试 | 7.5 | 8.0 | 组件测试较多，缺真实浏览器视觉回归 |
| 性能与大数据量 | 6.0 | 6.0 | 图、长 trace、大表格尚缺虚拟化/分段加载 |

后续实施补充：前端已增加标准化 SEC Financial Trend，展示 TTM/年度/季度优先值、同比/环比、reported/derived lineage 和数据覆盖警告；风险报告已展示未量化的财务传导通道；“Risk Score”已改称“Research Priority Score”，novelty 无历史时显示 N/A。新增 Research Journal 一级入口，可记录 thesis、证伪条件、监控指标、Watchlist 和 supported/mixed/invalidated 复盘。情景估值已作为折叠式分析区接入，仅预填 SEC 基线，所有核心估值假设必须由用户输入。管理层季度比较 UI 已接入，用户明确选择两个季度后可查看 prepared/Q&A/guidance/topic 的 evidence-linked 变化。自动提醒仍缺。

## 7. 高优先级行动

### P0（本轮已实施）

- 完整展示结构化风险报告字段；
- 将风险报告 claims 接入 Claim–Evidence Matrix；
- 顶部新增研究就绪度和分析师摘要；
- 为新增路径补组件测试和构建验证。

### P1

- 增加季度对比页：财务指标、管理层措辞、风险和 guidance diff；
- 把 Timeline/Trace/Evaluation 收纳到可展开的审计区；
- 增加风险到收入、利润率、EPS、FCF 的影响映射；
- 增加公司级 Research Questions 状态管理。

### P2

- Watchlist、催化剂日历、证伪条件与提醒；
- 估值与情景分析页；
- 多公司比较；
- Playwright 多视口、键盘、可访问性和视觉回归。

## 8. 验收标准

- 一个分析师在 30 秒内能够识别最高优先级风险、研究质量状态、最新变化和下一步问题；
- 每个关键结论可以在两次交互内定位到来源；
- 工程 trace 默认不抢占研究结论的视觉层级；
- 桌面、平板、手机均无不可达操作；
- 键盘可以完成导航、启动流程、选择历史 run 和查看证据；
- 对缺数据、失败、fallback 和需要人工复核提供明确下一步动作。
