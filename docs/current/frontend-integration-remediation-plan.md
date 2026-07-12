# 前端功能完整性与真实浏览器修复方案

状态：完成

制定日期：2026-07-12

目标：把当前“核心路径可演示”的前端提升为“项目能力可发现、关键操作可闭环、真实浏览器可持续运行”的个人分析师工作台；所有结论以运行中的 FastAPI、真实 Chromium 和生产构建为准，不以 fixture 单测代替验收。

基线：

- [分析师工作台能力路线图](analyst-workbench-roadmap.md)
- [发布就绪与能力深化方案](release-readiness-roadmap.md)
- [前端评估](assessments/frontend-assessment-2026-07-11.md)
- 2026-07-12 真实浏览器审计：1440、1024、390px；FinRisk 与 Supply Chain 真实运行；默认 API 限流与移动端遮挡复现。

## 0. 当前执行状态

| 工作包 | 状态 | 当前证据 | 退出条件 |
| --- | --- | --- | --- |
| 功能覆盖 | 完成 | Scenario、Sensitivity、Multiple、DCF、assumption history、Expectation–Actual、Peer 删除、workflow trace/artifacts 均有 UI | 已满足 |
| 请求与失败恢复 | 完成 | GET in-flight 去重与短缓存；`Retry-After`；局部保留；按需挂载；run-level trace 聚合 | 已满足 |
| Workbench 信息架构 | 完成 | Cycle、Valuation、Peer analysis、Reviews 任务导航并同步 URL | 已满足 |
| 响应式与浮层 | 完成 | 1440、1024、390px Chromium；移动 dock 回归文档流并默认折叠 | 已满足 |
| 可访问性与文案 | 完成 | skip link、focus-visible、reduced motion、live status、可行动错误、运维边界 | 已满足 |
| 自动化与真实验收 | 完成 | 75 frontend tests、968 backend tests、build、audit、两套 Chromium smoke | 已满足 |

## 1. 产品与设计判断

具体对象：持续跟踪公司风险、财务、估值和投资假设的个人分析师。

页面的单一任务：让分析师从“本期发生了什么变化”进入证据、假设、比较和复盘，而不是展示系统内部模块清单。

### 1.1 视觉系统

保留现有研究终端语言，不进行与修复目标无关的品牌重做：

| Token | 色值 | 用途 |
| --- | --- | --- |
| Midnight | `#0d1822` | 顶栏、运行状态 |
| Blueprint | `#dfe9ef` | 工作区背景与结构网格 |
| Paper | `#f7fafc` | 研究卡片 |
| Signal teal | `#087f8c` | 当前阶段、焦点和主要行动 |
| Review amber | `#b86b00` | 需要人工复核 |
| Failure red | `#b42318` | 可恢复失败 |

- 标题：现有 condensed/monospace utility 语言，用于研究阶段和数据标签。
- 正文：系统 sans，保证密集表单和表格可读性。
- 数据：monospace，仅用于 ticker、期间、数值和 lineage，不用于长说明。

### 1.2 布局方案

桌面：保持“研究记忆 + 当前研究阶段”的双栏关系；研究阶段内部采用任务导航，而不是继续向单页追加模块。

```text
┌────────────── global workspaces ──────────────┐
│ Research Journal                              │
├──────── thesis memory ─┬─ research task nav ──┤
│ active thesis          │ Cycle | Valuation    │
│ watchlist              │ Peers | Reviews      │
│ reminders              ├──────────────────────┤
│                        │ active task content   │
└────────────────────────┴──────────────────────┘
```

移动端：全局导航、研究记忆和任务内容自然纵向排列；运行监视器成为可折叠的文档流元素，不固定覆盖输入控件。

签名元素：保留 evidence-first 的 blueprint 网格与 `NODE` 标记，但只让它表达“研究对象/证据节点”的结构含义，不继续作为无差别装饰。

自检：该方向不引入常见的营销页 hero、渐变统计卡或无意义编号；改动服务于金融研究的时间顺序、证据关系和高密度数据操作。

## 2. 已确认问题

### 2.1 P0：默认限流破坏工作台加载

Research Journal 首次加载会并行请求 Thesis、Watchlist、Reminder、Alert、Draft、Peer Group 等资源。App 的隐藏视图保持挂载，切换和多页面访问会继续放大请求。默认 `RATE_LIMIT_RPM=120` 下，真实 Chromium 已出现连续 429，最终只显示笼统的 `could not be loaded`。

修复：

1. API client 为同一 GET 建立 in-flight 去重和短时缓存。
2. 解析 `Retry-After`，在错误对象中暴露 `retryAfterSeconds`。
3. 工作区只在激活时加载/轮询；隐藏工作区不得产生后台请求。
4. Research Journal 各数据组保留已成功数据，失败不得清空整个页面。
5. 错误组件说明原因、恢复时间并提供显式 Retry。

### 2.2 P0：移动端固定层遮挡

390px 下 `Current Agent` 和运行历史抽屉覆盖 Thesis、Research Cycle 与 provider 表单；部分行级控件被裁切。

修复：

1. 小于 700px 时 Current Agent 回到文档流并允许折叠。
2. 历史抽屉使用完整模态/显式开关，不保留侵入内容的窄轨道。
3. toolbar 和表单 grid 在移动端变为单列；按钮不得依赖横向空间。
4. 表格使用带可访问说明的局部滚动容器。

### 2.3 P0：后端功能没有前端闭环

必须补齐：

- P/E、EV/EBITDA、FCF yield Multiple Valuation。
- 简化 DCF。
- Valuation Assumption History。
- Peer Group 删除。
- Expectation 与实际财务值的 surprise 比较。
- Workflow trace、步骤输出和 artifact 统一入口。

保留为后端/运维职责而不伪装成分析功能：数据库迁移、备份、恢复、systemd/launchd 安装、服务端密钥和 TLS 配置。前端应在帮助文案中明确边界，不需要把危险运维操作暴露到浏览器。

### 2.4 P1：信息架构和错误状态

1. Research Journal 使用任务 tabs：Cycle、Valuation、Peers、Reviews。
2. 空态给出下一步，不使用只有情绪的空白文案。
3. 错误区分认证、限流、网络、服务端和数据不可用。
4. 操作名称和结果名称一致，例如 `Delete peer group` 后显示 `Peer group deleted`。

## 3. 实施顺序

### 工作包 A：API contract 与请求层

- 增加 Multiple、DCF、assumption history、Peer delete 的 TypeScript contract。
- GET 去重与可控 TTL 缓存；mutation 后失效相关缓存。
- `FinRiskApiError` 保存 HTTP 状态、响应 detail、`Retry-After`。
- 为 401、429、5xx 和网络错误生成面向用户的恢复说明。

### 工作包 B：估值工作台

- 在 Scenario Valuation 下增加方法导航。
- 所有输入保持 analyst-entered，不自动推断价格、WACC、terminal growth 或分母。
- 结果展示 method、value、unit、status、warnings/disclaimer。
- 保存并展示 assumption history；明确 as-of 和来源。

### 工作包 C：Research Journal 与 Peers

- 引入研究任务导航，避免单页无限堆叠。
- Peer Group 支持确认删除和删除后选择状态清理。
- 数据组独立加载与重试，局部失败不阻断其他研究任务。

### 工作包 D：响应式和可访问性

- 修复全局浮层、历史抽屉、toolbar、表单 grid 和长文本。
- `:focus-visible` 可见；skip link 可跳过全局导航。
- `prefers-reduced-motion: reduce` 禁用非必要 transition/animation。
- 状态不只使用颜色；图标按钮拥有 accessible name。

### 工作包 E：验证

自动化：

```bash
cd frontend
npm test -- --run
npm run build
npm audit --audit-level=moderate
```

真实浏览器：

| 视口 | 必须验证 |
| --- | --- |
| 1440×1000 | 四工作区、Research task tabs、估值和 Peer 操作 |
| 1024×900 | 双栏收缩、工具栏换行、表格滚动 |
| 390×844 | 无浮层遮挡、单列输入、所有主要按钮可达 |

运行态：

- console 无未处理错误。
- document 无整体横向溢出。
- 快速切换四个工作区不触发 429。
- 429 mock 显示等待时间和 Retry，成功数据不被清空。
- 真实 FinRisk 和 Supply Chain 各完成一次并渲染结果。

## 4. 完成定义

只有同时满足以下条件才能把本文状态改为“完成”：

1. 本文列出的缺失业务能力均有可发现的前端入口和测试。
2. 默认 API 限流下快速切换工作区不出现 429；注入 429 时有可恢复 UI。
3. 1440、1024、390px 截图证明无固定层遮挡和页面级横向溢出。
4. 键盘可到达所有主要操作，焦点可见，reduced-motion 生效。
5. frontend unit、production build、npm audit 全部通过。
6. 真实运行的 FastAPI、Vite、vLLM、Neo4j 路径完成 FinRisk 与 Supply Chain 浏览器 smoke。
7. 更新本文执行状态和验证记录；不能用“未发现问题”代替逐项证据。

## 5. 验证记录

完成日期：2026-07-12。

详细证据：[前端修复真实验收](validation/frontend-remediation-2026-07-12.md)。

- `75 passed` frontend tests。
- `968 passed, 6 skipped` backend tests。
- production build 通过；`npm audit` 0 vulnerabilities。
- `npm run test:workbench` 通过：1440×1000、1024×900、390×844，无 console/HTTP error、无页面级横向溢出、快速切换无 429。
- `frontend/e2e/real-mode.cjs` 通过：真实 vLLM FinRisk 与 Supply Chain。
