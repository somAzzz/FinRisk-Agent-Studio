# FinRisk-Agent-Studio 文档中心

这里是项目文档的统一入口。阅读时优先从“当前状态”开始；历史实施规格用于理解设计契约；已完成或已被替代的计划统一放在历史归档中。

## 当前状态

- [项目评估](current/assessments/project-assessment-2026-07-11.md)：从个人金融分析师视角评估当前能力、短板与方向。
- [前端评估](current/assessments/frontend-assessment-2026-07-11.md)：研究工作台的交互、信息架构与可用性评估。
- [发布就绪与能力深化方案](current/release-readiness-roadmap.md)：当前差距、同行分析、实施顺序与发布门禁。
- [分析师工作台能力路线图](current/analyst-workbench-roadmap.md)：已实现能力、当前阶段与完成定义。
- [前端功能完整性与真实浏览器修复方案](current/frontend-integration-remediation-plan.md)：前端功能闭环、失败恢复与三视口验收。
- [前端修复真实验收](current/validation/frontend-remediation-2026-07-12.md)：真实 Chromium、vLLM 流程与回归证据。
- [Research Journal 本地 LLM 全链路验收](current/validation/research-journal-live-2026-07-12.md)：隔离数据、真实浏览器与 7 次本地 LLM 调用证据。
- [个人研究闭环实施记录](current/research-closure-plan.md)：已完成首版闭环的实现契约与验收基线。
- [SEC 财务快照验证](current/validation/sec-financial-snapshot-2026-07-11.md)：AAPL、NVDA、XOM 的公开数据验证记录。
- [研究闭环真实数据矩阵](current/validation/research-closure-live-matrix-2026-07-11.md)：六类公司与 Watchlist 去重验证。
- [财务勾稽矩阵](current/validation/financial-reconciliation-2026-07-11.md)：五家公司、行业模板、IFRS 与 restatement 验证。
- [候选发布审计](current/validation/release-audit-2026-07-11.md)：自动化门禁、依赖审计与浏览器阻塞项。

详见 [current/README.md](current/README.md)。

## 使用指南

- [Agent 工作流](guides/agent-workflow.md)
- [演示脚本](guides/demo-script.md)
- [EDGAR 语料接入](guides/edgar-corpus.md)
- [个人研究闭环使用指南](guides/research-cycle.md)
- [Research Journal 本地 LLM 可复用验收](testing/research-journal-live-acceptance.md)

## 运维与安全

- [Docker 镜像固定策略](operations/deployment/docker-image-pinning.md)
- [安全限制与已知边界](operations/security/known-limitations.md)

## 历史实施规格

`specs/` 按 Risk Studio、Research Intelligence 和 Agent Runtime 三个能力阶段保存实现规格。目录里的旧编号只是历史 ID，不是产品版本。建议先阅读 [历史实施规格索引](specs/README.md)。

产品发布采用语义化版本，目前状态为 `Unreleased`。详见 [产品版本策略](VERSIONING.md)。

## 参考资料

- [SGLang 原生接口参考](reference/sglang_native_reference.py)

## 历史归档

`history/` 保存旧架构路线、历史实施计划、阶段审计、验证记录和设计草案。这些材料用于追溯决策，不代表当前优先级。详见 [历史归档索引](history/README.md)。

## 维护约定

- 当前仍指导开发或决策的文档放入 `current/`。
- 稳定的使用说明放入 `guides/`，部署与安全说明放入 `operations/`。
- 新设计按能力名称组织；旧 `specs/vXX-*` 目录只作为稳定的历史 ID 保留。
- 已完成、被替代或仅用于追溯的材料移入 `history/`，保留原始日期。
- 新增或移动文档时，同步更新本页及仓库内引用路径。
