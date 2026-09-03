# FinRisk Pydantic AI 与气候披露迁移教程（Chapter 6–16）

这套教程包含两条连续但不同的实践线：Chapter 6–9 从迁移前的真实 FinRisk 仓库出发，
完成可删除旧代码、可通过回归测试的 Pydantic AI 架构重构；Chapter 10–16 从完成后的
runtime 基线出发，把 `llm_tcfd` 的研究能力选择性迁入 FinRisk，形成可追溯的气候披露领域。

先读[完整学习指南](COMPLETE_GUIDE.md)。学习 runtime 重构时使用
[Pydantic AI 迁移总图](MIGRATION_MAP.md)；学习气候领域合并时使用
[气候披露迁移总图](CLIMATE_MIGRATION_MAP.md)。每章都明确列出文件、合同、测试、Gate
和提交边界。

## 推荐起点

### Chapter 6–9：重演 runtime 迁移

当前分支已经包含最终 Pydantic AI runtime，适合对照结果，不适合直接练习旧 runtime
切换。推荐从第一次 Pydantic AI 提交之前的提交创建学习分支：

```bash
git switch -c learn/pydantic-ai-refactor \
  023c02f91be43ecf6428d12e5dac3272569a62b3
uv sync
uv run pytest -q
```

不要在开始前阅读后续迁移提交的实现。完成每章并通过验收后，再用当前 `main` 或
`tutorial/pydantic-ai-harness` 分支作设计对照。

### Chapter 10–16：实施气候披露合并

从已经完成 Chapter 9 的 FinRisk 代码开始，并固定 TCFD 源仓库 revision：

```text
FinRisk code baseline: 145e34b2e3a39cf78f78a226f20108c97d30962d
TCFD source baseline:  4ef1c0f49853d2821dbf1ead73259d65475ca8d3
```

这组章节目前是实施教程，不是已经存在的答案代码。练习者使用后续 revision 时，应在
provenance manifest 写自己的完整 SHA，而不是继续复制上述参考值。

## 章节与累计产物

| 章节 | 核心结果 | 主要替代对象或新增能力 |
| --- | --- | --- |
| [6. Typed Toolsets](06-toolsets.md) | model factory、typed deps、typed tools、权限与 trace | 业务代码直接选择 provider、手写工具 schema、`src/llm/tool_loop.py` 的工具执行职责 |
| [7. Specialists](07-specialists.md) | typed specialist Agents、Pydantic Graph、正式 cutover | generic JSON/completion client、手写 planner/tool loop、自由文本 Agent 边界 |
| [8. Harness](08-harness.md) | Core baseline 与选定 Harness capabilities 的实测集成 | 只替代被实验证明冗余的编排/上下文辅助代码，不替代领域状态机 |
| [9. Production](09-production.md) | guardrails、审批、memory 隔离、trace、eval 与发布门禁 | 临时安全检查、不可审计审批、把 memory 当 evidence、人工目测迁移质量 |
| [10. Integration Boundaries](10-integration-boundaries.md) | 仓库边界、许可、数据 inventory、provenance | 机械合并和跨仓库运行时依赖 |
| [11. Evidence Contracts](11-evidence-contracts.md) | document、locator、climate evidence、mapping、独立 state | 把候选或风险 evidence 当最终披露证据 |
| [12. Document Ingestion](12-document-ingestion.md) | SEC/TXT/A 股 adapter、block-aware chunking、PDF/OCR issue | 只读 Item 1A、裸字符串 chunk 和文件名主键 |
| [13. Registry & Retrieval](13-registry-retrieval.md) | 标准 registry、跨框架 mapping、混合召回 | A/B 共现作为全局门和散落 prompt 标准规则 |
| [14. Climate Agents](14-climate-agents.md) | typed evidence extractor、verifier、确定性 metric parser | keyword/binary relevance 直接决定披露状态 |
| [15. Assessment & Product](15-assessment-product.md) | 五状态聚合、报告、API、HITL、前端 | 单一总分和第二套 TCFD 产品入口 |
| [16. Shadow & Cutover](16-shadow-cutover.md) | 分层 eval、shadow、release gate、rollback | 用测试通过或单一 accuracy 宣布合并完成 |

Chapter 6–9 是同一学习分支上的累计 runtime 重构；Chapter 10–16 是另一条从完成态开始的
累计领域迁移。不要把两个起点混成一条包含旧 runtime 和新 climate state 的长期分支。

## 实施约束

- typed Python 签名和 Pydantic model 是新合同的真相源，不从旧 JSON schema 反向生成。
- 只保留明确列出的领域/API 合同；不为旧 Python 类、旧调用参数或旧 runtime flag
  创建长期兼容层。
- 新路径通过验收后删除旧实现与旧测试，禁止保留双 runtime。
- LLM 负责发现、选择、结构化和解释；证据确认、权限、预算、评分、图校验和发布门禁
  仍由确定性代码负责。
- `src/domains/climate` 保持模型无关；Pydantic AI Agent 放在 `src/ai/agents/climate`。
- FinRisk 不 import、安装或在运行时读取 TCFD 工作区；所有移植项先过许可和 provenance gate。
- 教程提供合同、实现顺序和测试要求，不提供可直接复制的主体答案代码。

## 版本基线

- Python：`3.12`
- 当前 Pydantic AI 锁定版本：`pydantic-ai-slim 2.33.0`
- Chapter 8 建议实验版本：`pydantic-ai-harness 0.27.0`
- Harness 仍为 `0.x`；升级 minor 版本前必须读 release notes 并重跑 Chapter 8–9
  的 contract/eval tests。

版本信息校对日期为 2026-09-03。实际实现时以 `uv.lock` 与官方文档为准。

## 每章提交建议

```text
ch06: establish typed model deps and tool boundaries
ch07: cut over to typed specialist agents and graphs
ch08: evaluate and integrate selected harness capabilities
ch09: add production governance trace and migration evals
ch10: fix climate migration ownership and provenance
ch11: establish climate disclosure evidence contracts
ch12: add traceable disclosure ingestion adapters
ch13: add reviewed requirements and hybrid climate retrieval
ch14: add typed climate evidence extraction and verification
ch15: add deterministic climate assessment and product workflow
ch16: validate shadow and cut over climate disclosure workflow
```

每章只在 DoD 全部通过后提交。Chapter 7 必须证明旧 runtime 已真正删除；Chapter 16 必须
证明 FinRisk 没有 TCFD 运行时依赖、肯定结论可回源且回滚已演练。
