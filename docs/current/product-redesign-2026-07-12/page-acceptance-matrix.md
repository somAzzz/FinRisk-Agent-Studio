# 高保真页面验收矩阵

基准桌面视口：1440 × 1024
基准移动视口：390 × 844
Overview 母版复核视口：1487 × 1058
视觉母版：`company-workspace-target.png`

## 全局结构

| 区域 | 桌面规则 | 移动规则 | 验收结果 |
|---|---|---|---|
| Sidebar | 232px 深色固定列 | 64px 顶栏 + 展开菜单 | 通过；四个主路由、Activity、Runtime settings 可达 |
| Company header | 约 140px，Identity / Health / CTA 三段 | 单列，CTA ≥44px | 通过；真实状态表达，Run update 打开 Drawer |
| Company tabs | 54px 单行 | 横向滚动 | 通过；七个子路由可前进/后退 |
| Content canvas | Overview 16px、其他产品页 32px | 16px | 通过；无 fixed 遮挡和页面级横向溢出 |

## 页面验收

| 页面 | 单一任务 | 核心功能 | 桌面 | 移动 | 状态 |
|---|---|---|---|---|---|
| Today | 确定今天的研究优先级 | Review、Start research、View runs | `today-desktop-current.jpg` | `today-mobile-current.jpg` | 通过 |
| Company Overview | 理解最新公司风险位置 | 子页切换、Run update、Risks、Evidence、Trace | `overview-desktop-current.jpg` + 原尺寸图 | `overview-mobile-current.jpg` | 通过 |
| Risks | 深入查看风险与变化 | 选择风险、查看证据 | `risks-desktop-current.jpg` | `risks-mobile-current.jpg` | 通过 |
| Financials | 查看标准化事实与变化 | 指标与 lineage、warning 展开 | `financials-desktop-current.jpg` | `financials-mobile-current.jpg` | 通过 |
| Valuation | 管理显式假设 | Scenario、Sensitivity、Multiple、DCF | `valuation-desktop-current.jpg` | `valuation-mobile-current.jpg` | 通过 |
| Management | 对比管理层口径 | Compare calls | `management-desktop-current.jpg` | `management-mobile-current.jpg` | 通过 |
| Supply Chain | 查看产品依赖与证据 | Run、选择节点、扩展节点 | `supply-chain-desktop-current.jpg` | `supply-chain-mobile-current.jpg` | 通过 |
| Evidence | 审核 Claim 与证据 | Release gate、source inventory、technical detail | `evidence-desktop-current.jpg` | `evidence-mobile-current.jpg` | 通过 |
| Research Runs | 判断运行可信度并完成复核 | Run brief、Run Agent、trace、candidate/review | `research-journal-redesign-audit/04-runs-after-desktop.jpg` | `research-journal-redesign-audit/06-runs-after-mobile.jpg` | 通过 |
| Journal | 维护可证伪的长期研究记忆 | Journal brief、thesis、快照、比较、复盘 | `research-journal-redesign-audit/05-journal-after-desktop.jpg` | `research-journal-redesign-audit/07-journal-after-mobile.jpg` | 通过 |

## 统一质量门槛

- 全部页面已有桌面截图、移动截图和主要交互验证。
- 全部页面使用同一 token、字号、图标、表单和反馈体系。
- 静态演示使用明确且互相一致的 fixture，不伪装实时数据，不显示不可恢复的 API 错误。
- `npm run build` 通过；18 个测试文件、76 项测试通过。
- 当前无 P0/P1/P2，`design-qa.md` 已标记 `final result: passed`。
