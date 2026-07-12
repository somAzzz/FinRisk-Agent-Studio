# 前端功能完整性修复真实验收

日期：2026-07-12

对应方案：[前端功能完整性与真实浏览器修复方案](../frontend-integration-remediation-plan.md)

## 1. 功能闭环

| 能力 | 证据 | 结果 |
| --- | --- | --- |
| Scenario 与 Sensitivity | `ScenarioValuationPanel` + component tests | 通过 |
| P/E、EV/EBITDA、FCF yield | `/research/valuation/multiple` + UI + live browser | 通过 |
| DCF | `/research/valuation/dcf` + UI + live browser | 通过 |
| Assumption history | `/research/valuation/history/{ticker}`；live AAPL 保存 multiple 与 DCF | 通过 |
| Expectation–Actual | compare API、UI surprise 展示、component test | 通过 |
| Peer lifecycle | 建立、二次确认删除、真实浏览器清理 | 通过 |
| Workflow observability | 每个 run 一次加载 trace/artifacts，再分发到 step inspector | 通过 |
| 运维边界 | 浏览器说明 migration/backup/restore/scheduler 保留在 CLI | 通过 |

## 2. 请求与失败恢复

- 同路径并发 GET 只发送一次；短 TTL 避免工作区快速重挂载重复请求。
- mutation 后使 GET cache 失效。
- `FinRiskApiError` 保存 response detail 与 `Retry-After`。
- 401/403、429、5xx、网络错误生成不同的恢复文案。
- Journal、Cycle、Ticker 数据使用独立 settled 结果，局部失败不清空已成功数据。
- 隐藏工作区不挂载，不产生后台组件请求。
- Evaluation trace 不再按 8 个步骤重复请求。

429 component test 验证等待秒数和 Retry；真实 Chromium 连续三轮切换四工作区没有产生 4xx。

## 3. 三视口浏览器验收

命令：

```bash
cd frontend
npm run test:workbench
```

| 视口 | 页面级横向溢出 | 固定层遮挡 | Console/HTTP error | 结果 |
| --- | --- | --- | --- | --- |
| 1440×1000 | 无 | dock 默认折叠 | 无 | 通过 |
| 1024×900 | 无 | dock 默认折叠 | 无 | 通过 |
| 390×844 | 无 | dock 为文档流元素 | 无 | 通过 |

自动检查还覆盖：skip link 首个键盘焦点、任务 URL 状态、reduced motion、AAPL snapshot 加载、Multiple、DCF、assumption history 和 Peer 建立/删除。

本地截图：

```text
artifacts/frontend-remediation/desktop-1440.png
artifacts/frontend-remediation/tablet-1024.png
artifacts/frontend-remediation/mobile-390.png
artifacts/frontend-remediation/valuation-live.png
```

## 4. 真实业务路径

```bash
cd frontend
node e2e/real-mode.cjs
```

结果：`Playwright real-mode frontend checks passed`，exit 0。

- FinRisk：`run-93fcbaabc502`，真实 AAPL，最终 `needs_review`。
- Supply Chain：`sc-run-55fe7e5f5e5e`，真实 NVIDIA/GPU，最终 `needs_review`。
- Research snapshot：`snapshot-33812950e6623976`，AAPL financial component complete，68 sources。
- AAPL valuation history 保存了 live Multiple 与 DCF assumptions。

`needs_review` 是质量门禁状态，不是 fixture 降级或执行失败。

## 5. 自动化回归

```text
frontend: 18 files, 75 passed
backend: 968 passed, 6 skipped
production build: passed
npm audit: 0 vulnerabilities
git diff --check: passed
```

跳过的 6 项均为需要显式环境开关或外部密钥的 SEC/transcript integration tests；SEC 真实路径已由 AAPL research snapshot 单独覆盖。
