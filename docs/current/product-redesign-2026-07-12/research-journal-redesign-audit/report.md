# Research Runs + Journal 产品设计审计与重构记录

审计日期：2026-07-12
视觉母版：Company Overview
桌面视口：1440 × 1024
移动视口：390 × 844

## Audit scope

- Research Runs：从选择运行、判断可信度，到处理证据与人工复核。
- Journal：从理解当前 thesis、查看复核节奏，到创建 thesis、生成快照与完成复盘。
- 对照上下文：Company 页面已经形成的石墨侧栏、四列 brief、teal/amber/red 语义和证据优先层级。

## User goal and accessibility target

- Runs 用户目标：在几秒内判断运行是否干净、证据是否充分、哪里需要人工判断。
- Journal 用户目标：持续维护可证伪的 thesis，并把 checkpoint、变化、证据和复盘串成长期记忆。
- 可访问性目标：清晰的标题顺序、语义按钮与表单标签、可见焦点、移动端可重排、主要操作不被横向裁切。

## Current-state findings

1. **Runs — P1：配置、历史和结果同权，核心判断不突出。**
   - Evidence: `02-runs-before.jpg` 中三列同时争夺首屏；运行完成后，配置表单仍占据最重要的位置。
   - Impact: 用户必须阅读多个技术容器，才能回答“可信不可信、下一步做什么”。
   - Fix: 将配置收进可展开的 Run configuration；新增四列 Run brief，把状态、证据、工具覆盖和下一步人工动作放在首屏。

2. **Runs — P2：执行轨迹和人工复核缺少主次关系。**
   - Evidence: 工具事件、Evidence Graph、Candidates、Human Review 都是同一种 section，人工判断被埋在长页面中。
   - Impact: 复核动作难发现，历史与当前运行也缺少关系。
   - Fix: 使用“Planner → source checks”的纵向执行主线，右侧固定 Human judgment / Evidence candidates；历史列表补充任务和复核摘要。

3. **Journal — P1：空白创建表单压过已有研究记忆。**
   - Evidence: `03-journal-before.jpg` 首屏左侧是六字段空表单，而 active thesis、证伪条件和 review cadence 在下方或不可见。
   - Impact: 产品更像数据录入工具，而不是研究决策记忆。
   - Fix: 先展示 Journal brief 和 Thesis spine；创建表单降级为可展开的 Create a thesis。

4. **Journal — P2：研究周期信息密集但缺少产品叙事。**
   - Evidence: dark segmented nav、紧凑 controls、snapshot/change/queue 以相近视觉重量连续出现。
   - Impact: 用户不容易区分当前立场、待复核事项与操作区。
   - Fix: 使用轻量 task tabs；把 active thesis、next review、open diligence、evidence linked 作为顶层 brief；变化使用红色 evidence rail，证伪条件使用 amber diligence surface。

## Implemented direction

- 沿用 Company 的 232px graphite sidebar、白色分析画布、细边框、8px radius、monospace metadata 和 evidence teal。
- Runs 的标志性结构是“执行主线 + 人工判断侧栏”；视觉风险集中在这条可审计的纵向 trace，而不是添加装饰。
- Journal 的标志性结构是 Thesis spine：statement、drivers、falsification conditions 与 review action 保持在一个连续研究对象中。
- 所有产品文案改为用户任务语言；配置细节、provenance 和 archive 降级为按需展开。

## Verification steps

| Step | Description | Health |
|---|---|---|
| 1 | Company 视觉母版与 token 参照 | Healthy |
| 2 | Runs 当前完成态审计 | Reworked |
| 3 | Journal 当前研究周期审计 | Reworked |
| 4 | Runs desktop：Run brief、execution trace、review queue | Healthy |
| 5 | Journal desktop：Journal brief、thesis spine、research cycle | Healthy |
| 6 | Runs mobile：brief 优先于历史，2×2 summary reflow | Healthy |
| 7 | Journal mobile：2×2 brief 后立即出现 thesis spine | Healthy |

## Interaction verification

- Runs：展开配置、Run Agent、候选证据 Approve、人工复核 Approve、review count 归零。
- Journal：展开 composer、新建 thesis、Create snapshot、进入 Reviews、Generate draft。
- 18 个测试文件、76 项测试通过；两个最终浏览器会话无 warning/error。

## Evidence limits

- 截图可以确认层级、密度、响应式和可见 affordance，不能单独证明完整 WCAG 合规。
- 键盘焦点、语义结构和按钮/表单标签通过实现与浏览器 DOM 检查；仍建议在真实后端数据量下追加长文本与大量历史记录测试。

## Artifacts

- `01-company-reference.jpg`
- `02-runs-before.jpg`
- `03-journal-before.jpg`
- `04-runs-after-desktop.jpg`
- `05-journal-after-desktop.jpg`
- `06-runs-after-mobile.jpg`
- `07-journal-after-mobile.jpg`
