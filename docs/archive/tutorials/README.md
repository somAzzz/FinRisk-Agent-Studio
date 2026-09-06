# FinRisk Pydantic AI 实现导读与气候披露归档教程（Chapter 0–16）

> 归档说明：本教程保留历史学习与架构推演材料，不代表 FinRisk 当前产品范围或路线图。
> 当前实现、状态和后续计划分别以 `docs/ARCHITECTURE.md`、`docs/STATUS.md` 和
> `docs/ROADMAP.md` 为准。

这套归档教程包含两类材料：Chapter 0–9 已按当前 `main` 改为 Pydantic AI 实现导读与
验证练习；Chapter 10 记录气候披露方案的重启门槛，Chapter 11–16 仍是未进入当前路线的
历史架构推演。

`COMPLETE_GUIDE.md`、`MIGRATION_MAP.md` 和 `CLIMATE_MIGRATION_MAP.md` 保留原迁移设计
背景；涉及当前代码、版本和完成状态时，以 Chapter 6–10、`docs/STATUS.md` 和
`docs/ROADMAP.md` 为准。

## 推荐起点

### Chapter 0–9：阅读和验证当前 runtime

当前分支已经包含唯一的 Pydantic AI runtime。推荐直接从当前代码和测试学习：

```bash
uv sync
uv run python -m pytest -q tests/ai
```

如需重演历史 cutover，再从 Git 历史定位迁移前 commit；不要把历史施工要求应用到当前
`main`，也不要重新引入已经删除的 runtime。

### Chapter 10–16：归档气候披露推演

历史参考基线是：

```text
FinRisk current review: 558e276f7880b081f64c4fecabdadc7212e3db59
TCFD source baseline:  4ef1c0f49853d2821dbf1ead73259d65475ca8d3
```

气候披露合并当前未列入路线图。Chapter 10 说明未来重启条件；Chapter 11–16 不应在未经
owner、许可和数据策略批准时直接实施。

## 章节与累计产物

| 章节 | 核心结果 | 学习重点 |
| --- | --- | --- |
| [0. Local Model](00-local-model.md) | deployment factory、`ModelSettings`、配置解析和 live probe | 手写练习 where/what、generation 与 usage 三类边界 |
| [1. Typed Agent](01-typed-agent.md) | 专用 typed outputs 与 client adapters | 从 `result.output` 到领域/workflow state |
| [2. Dependencies](02-dependencies.md) | run identity、subject、permissions、services 和 budget | 理解 per-run 对象所有权与 composition root |
| [3. Validation](03-validation.md) | schema、output validator、`ModelRetry`、guardrail 和失败语义 | 区分结构错误、可重试语义错误和业务降级 |
| [4. Programmatic Workflow](04-programmatic-workflow.md) | 三类 Pydantic Graph 与确定性 workflow | 明确模型与 Python 各自控制什么 |
| [5. Evals](05-evals.md) | 离线测试、golden cases、source gate 与 live acceptance | 区分架构、回归、协议和质量证据 |
| [6. Typed Toolsets](06-toolsets.md) | 当前 model factory、deps、catalog/toolset 与权限边界 | 理解双 schema 兼容现状和实际预算范围 |
| [7. Specialists](07-specialists.md) | 当前 typed Agents、adapters 与三类 Pydantic Graph | 验证单一 runtime 与 deterministic domain 边界 |
| [8. Runtime Integration](08-harness.md) | 同步 adapter、消息恢复、stream projection 与编排取舍 | 说明为何当前没有采用 Harness |
| [9. Production](09-production.md) | 当前审批、memory、trace、eval、live acceptance 及缺口 | 区分测试证据与尚未实现的生产保证 |
| [10. Integration Boundaries](10-integration-boundaries.md) | 气候方案当前状态与未来重启条件 | 防止归档计划被误当成当前产品范围 |
| [11. Evidence Contracts](11-evidence-contracts.md) | document、locator、climate evidence、mapping、独立 state | 把候选或风险 evidence 当最终披露证据 |
| [12. Document Ingestion](12-document-ingestion.md) | SEC/TXT/A 股 adapter、block-aware chunking、PDF/OCR issue | 只读 Item 1A、裸字符串 chunk 和文件名主键 |
| [13. Registry & Retrieval](13-registry-retrieval.md) | 标准 registry、跨框架 mapping、混合召回 | A/B 共现作为全局门和散落 prompt 标准规则 |
| [14. Climate Agents](14-climate-agents.md) | typed evidence extractor、verifier、确定性 metric parser | keyword/binary relevance 直接决定披露状态 |
| [15. Assessment & Product](15-assessment-product.md) | 五状态聚合、报告、API、HITL、前端 | 单一总分和第二套 TCFD 产品入口 |
| [16. Shadow & Cutover](16-shadow-cutover.md) | 分层 eval、shadow、release gate、rollback | 用测试通过或单一 accuracy 宣布合并完成 |

Chapter 0–9 面向当前实现；Chapter 10–16 是归档气候方案。不要把后者的目标目录和功能写成
仓库已完成能力。

## 实施约束

- typed Python 签名和 Pydantic model 是新合同的真相源，不从旧 JSON schema 反向生成。
- 只保留明确列出的领域/API 合同；不为旧 Python 类、旧调用参数或旧 runtime flag
  创建长期兼容层。
- 新路径通过验收后删除旧实现与旧测试，禁止保留双 runtime。
- LLM 负责发现、选择、结构化和解释；证据确认、权限、预算、评分、图校验和发布门禁
  仍由确定性代码负责。
- `src/domains/climate` 保持模型无关；Pydantic AI Agent 放在 `src/ai/agents/climate`。
- FinRisk 不 import、安装或在运行时读取 TCFD 工作区；所有移植项先过许可和 provenance gate。
- 教程以合同、实现顺序和测试要求为主；Chapter 0 额外提供用于手写训练的目标代码片段，
  但不应不经测试地整章复制进仓库。

## 版本基线

- Python：`3.12`
- 当前 `pydantic-ai` / `pydantic-ai-slim` 锁定版本：`2.27.1`
- 当前未安装 `pydantic-ai-harness`，Chapter 8 不要求增加它。

版本信息校对日期为 2026-09-06。实际实现时以 `uv.lock` 为准。

## 历史与文档提交参考

```text
docs(tutorials): explain the single model boundary
docs(tutorials): explain typed agent outputs
docs(tutorials): explain run-scoped dependencies
docs(tutorials): explain validation retry and failure semantics
docs(tutorials): explain programmatic graph workflows
docs(tutorials): explain offline and live evaluation boundaries
docs(tutorials): explain current model deps and typed tools
docs(tutorials): explain typed agents adapters and graphs
docs(tutorials): document runtime persistence and orchestration choices
docs(tutorials): document governance evidence and remaining gaps
docs(tutorials): record climate migration restart conditions
ch11: establish climate disclosure evidence contracts
ch12: add traceable disclosure ingestion adapters
ch13: add reviewed requirements and hybrid climate retrieval
ch14: add typed climate evidence extraction and verification
ch15: add deterministic climate assessment and product workflow
ch16: validate shadow and cut over climate disclosure workflow
```

Chapter 0–10 的检查命令用于复核当前实现。Chapter 11–16 若未来重新进入路线，必须先满足
Chapter 10 的 owner、许可、数据和 provenance 门槛。
