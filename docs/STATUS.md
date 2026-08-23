# FinRisk Agent Studio v0.1 项目状态

最后更新：2026-08-23

代码基线：`dc1646e`（`codex/product-design-redesign`）

发布状态：`v0.1` 候选，尚未发布；包版本为 `0.1.0`，仓库尚无产品 tag。

本文是项目完成状态的唯一当前口径。路线和后续优先级见 [ROADMAP.md](ROADMAP.md)，产品与技术边界见 [specs/v0.1.md](specs/v0.1.md)。

## 总体结论

FinRisk Agent Studio 已形成可运行的 evidence-first 个人金融研究工作台。核心研究闭环、风险工作流、财务事实、同行分析、估值、供应链图谱、监控和多页面前端已经实现。

当前工作重点不再是补齐基础功能，而是：

1. 将产品重设计分支合入 `main`；
2. 在合并候选上重跑发布门禁；
3. 完成 Agent 长期记忆与失败恢复；
4. 清理全仓历史 lint 债务；
5. 明确并创建首个 `v0.1.0` 发布 tag。

## 完成状态

状态含义：

- **完成**：v0.1 定义范围已经实现并有自动化或真实验收证据。
- **核心完成**：主路径可用；外部 provider、规模化或高级能力不阻塞 v0.1。
- **进行中**：已有实现，但尚未达到退出条件。
- **外部限制**：正确降级已实现，完整结果依赖外部数据、密钥或服务。

| 目标 | 状态 | 已实现结果 | 剩余工作 |
| --- | --- | --- | --- |
| 证据与数据基础 | 核心完成 | SEC、filing sections、transcript、XBRL、web/search/browser、缓存和 lineage | inline XBRL 分部维度、更多稳定 provider |
| FinRisk 风险工作流 | 完成 | 八步工作流、确定性评分、报告、质量门禁、人工复核 | 持续扩充真实回归样本 |
| 图推理与供应链 | 核心完成 | 路径检索、证据绑定、递归供应链、Sankey、图写入边界 | 扩大真实供应链覆盖和 Neo4j 长期验证 |
| LLM Tool Loop | 完成 | provider-neutral 工具调用、预算、JSON fallback、trace | provider 兼容性维护 |
| Agent Runtime | 进行中 | Pydantic AI typed provider/deps/tools/output、typed planner/filing/supply-chain primary、Pydantic Graph、服务端 conversation resume、SQLite 原子 deferred approval、legacy/primary 开关 | 有效 live provider 验收、发布观察期、默认切换与 legacy 退役 |
| 个人研究闭环 | 完成 | snapshot、change、Thesis、Watchlist、expectation、alert、复盘 | 维护 point-in-time 与幂等回归 |
| 财务/同行/估值/监控 | 核心完成 | 六类行业模板、五公司勾稽、Peer Group、四类估值、调度模板 | consensus、自动 FX、分部 KPI、长期校准 |
| 产品工作台 | 完成，待主线集成 | Today、Company、Runs、Journal 十条路由，桌面/移动 QA | 合入 `main` 后复跑浏览器门禁 |
| 工程与发布 | 进行中 | CI、数据库迁移/恢复、静态部署、测试与安全边界 | 全仓 Ruff 治理、发布审计和 tag |

## 已完成的核心闭环

```text
SEC / Transcript / Market / Graph
→ FinRisk Workflow
→ Evidence Normalization + Quality Gate
→ CompanyResearchSnapshot
→ ResearchChange + Human Review
→ Expectation + Valuation + Thesis
→ Watchlist Scan + Deduplicated Alert
→ Post-earnings Review
→ Journal
```

关键约束：

- 所有重要事实保留 source、as-of、lineage 和 component status。
- reported、derived、provider、user-entered 和 model interpretation 不混为同一种事实。
- provider 缺失不生成“风险已消失”或“没有变化”的结论。
- LLM 不创建无证据 confirmed graph edge，也不输出买卖建议。
- 质量门禁可以把结果降级为 `needs_review`，这不是执行失败。

## 子系统完成情况

### 数据与证据

- SEC/EDGAR、Company Facts、filing section 和历史 CIK continuity 已接入。
- Transcript、搜索、网页抓取和浏览器探索支持 provider fallback。
- 财务事实支持 original、amended、latest-known 三种 restatement 语义。
- AAPL、NVDA、XOM、JPM、TSM 已完成公开数据勾稽。
- SEC Company Facts 不提供完整 segment axis；系统保持 N/A，不推断分部数据。

### 风险、质量与图

- Company Resolver → Filing Risk → Market Evidence → Normalization → Scoring → Graph → Report → Evaluation 已接通。
- schema、claim grounding、source quality、financial safety、graph path 和 fallback 由 runtime guardrail 检查。
- 供应链支持递归扩展、Sankey payload、证据引用和候选/确认图边边界。
- 30 个离线 golden cases 覆盖行业、异常 filing、来源冲突和安全边界。

### Agent 与记忆

- `/agent-runs` 提供运行、timeline、trace、候选证据和人工复核接口。
- Tool Loop 支持 OpenAI-compatible provider、native tool calling、JSON fallback 和预算限制。
- Pydantic AI primary 已在 feature flag 后接入，13 个工具具有 typed schema、
  权限过滤和 legacy contract parity；FinRisk/Supply Chain 顺序图已通过 demo parity。
- typed planner、filing risk chunk 与 supplier relation extraction 已接入 primary；
  graph/report 保持既有确定性计算，避免为迁移新增非确定性模型调用。
- Agent message batch、服务端 conversation resume、usage recorder 和 deferred
  approval 已有 SQLite/in-memory 合同、重启恢复、并发单次领取与 replay protection。
- 每个 Agent run 记录实际 runtime mode；live provider 合同和 20-run/168-hour
  primary observation gate 已提供机器可读报告与 fail-closed 退出码。
- evidence memory、graph-edge memory 和 active/candidate lifecycle 已有工程实现。
- 长期记忆检索质量、过期策略、跨进程恢复和长时间无人值守仍属于 v0.2 范围。

### 研究工作台

- Research Cycle 可以启动 FinRisk、创建不可变快照并保留 correlation ID。
- Thesis、Watchlist、Expectation、Alert、Peer Group、估值假设和复盘均可持久化。
- Peer Analysis 分离财务、风险、预期和估值，不生成单一“神奇分数”。
- Today、Company、Research Runs、Journal 已形成任务导向的信息架构。

## 当前验证基线

| 检查 | 最近结果 | 日期 |
| --- | --- | --- |
| 后端非集成测试 | `1036 passed, 1 skipped, 8 deselected` | 2026-08-23 |
| 前端测试 | 18 files，`76 passed` | 2026-07-25 |
| TypeScript + Vite production build | 通过 | 2026-07-25 |
| 三视口 Chromium 与交互 | 通过 | 2026-07-12 |
| Research Journal 本地 LLM 全链路 | 通过 | 2026-07-12 |
| 财务勾稽 | AAPL/NVDA/XOM/JPM/TSM 通过既定矩阵 | 2026-07-11 |
| Golden cases | 30/30 | 2026-07-12 |
| npm audit | 0 vulnerabilities | 2026-07-12 |
| 全仓 Ruff | 166 个历史告警，CI 中为 advisory | 2026-07-23 |

详细证据：

- [财务勾稽](validation/financial-reconciliation.md)
- [前端验收](validation/frontend-acceptance.md)
- [Research Journal 本地 LLM 验收](validation/research-journal-live.md)
- [真实数据验收方法](testing/real-data-acceptance.md)
- [Pydantic AI PAI-7 切换准备](validation/pydantic-ai-pai-7-readiness.md)

## 已知限制

1. 当前产品分支比 `main` 多 1 个提交，尚未形成主线发布候选。
2. live SEC、transcript、search、Neo4j 和 LLM 路径需要外部服务、网络或密钥。
3. SEC Company Facts 的分部维度不足，不能自动生成可靠 segment facts。
4. 外部 consensus、自动 FX 和外部通知尚未成为默认能力。
5. Agent memory 已有基础实现，但长期反馈质量和恢复能力尚未达到生产级。
6. 全仓 Ruff 尚未归零；当前 CI 只阻塞变更 Python 文件的新问题。
7. 项目不提供投资建议、交易执行或自动仓位管理。

## v0.1 发布前必须完成

1. 将 `codex/product-design-redesign` 合入 `main`。
2. 在合并候选上通过后端测试、前端测试、生产构建和变更文件 Ruff。
3. 重跑 npm audit、三视口浏览器 smoke 和至少一条真实模式验收。
4. 核对数据库迁移、备份和恢复。
5. 更新本页验证日期并确认跳过项。
6. 创建 `v0.1.0` Git tag 后，才可把状态改为“已发布”。
