# FinRisk Agent Studio v0.1 文档

文档已按小版本 `v0.1` 重新整理。当前状态、路线图和规格各有一个唯一入口，不再保留 `v15–v21` 实施编号或已完成计划。

## 核心文档

1. [项目状态](STATUS.md)：目标、子系统完成情况、验证基线和已知限制。
2. [路线图](ROADMAP.md)：v0.1 发布条件及 v0.2–v0.4 方向。
3. [系统架构](ARCHITECTURE.md)：产品域、服务、数据、工作流和安全边界。
4. [v0.1 规格](specs/v0.1.md)：当前版本的功能与验收契约。
5. [版本策略](VERSIONING.md)：文档小版本、包版本和 Git tag 的对应关系。
6. [Pydantic AI 迁移完成记录](PYDANTIC_AI_MIGRATION.md)：单一生产 Agent runtime、已删除旧路径、验收证据和维护约束。
7. [Pydantic AI 单一运行时 ADR](ADR_PYDANTIC_AI_RUNTIME.md)：模型边界、项目侧治理职责和部署回滚决策。
8. [Pydantic AI 切流与回滚 Runbook](guides/pydantic-ai-cutover.md)：live provider 合同、切换与回滚操作记录。
9. [TCFD 气候披露能力合并方案](migration/tcfd-integration-plan.md)：FinRisk 与 `llm_tcfd` 的职责边界、可复用能力、重构范围、分步门禁和切换策略。
10. [Pydantic AI 与气候披露迁移教程](../tutorials/README.md)：Chapter 6–9 runtime 重构和 Chapter 10–16 气候领域合并实践。

## 使用指南

- [个人研究闭环](guides/research-cycle.md)

## 测试与验收

- [真实数据验收](testing/real-data-acceptance.md)
- [Research Journal 本地 LLM 验收方法](testing/research-journal-live-acceptance.md)
- [财务勾稽结果](validation/financial-reconciliation.md)
- [前端验收结果](validation/frontend-acceptance.md)
- [Research Journal 本地 LLM 验收结果](validation/research-journal-live.md)

## 运维与安全

- [Docker 镜像固定](operations/deployment/docker-image-pinning.md)
- [安全限制与已知边界](operations/security/known-limitations.md)

## 参考

- [SGLang 原生接口参考](reference/sglang_native_reference.py)

## 维护规则

- 当前完成状态只在 `STATUS.md` 更新。
- 未来计划只在 `ROADMAP.md` 更新。
- v0.1 的产品和技术契约只在 `specs/v0.1.md` 更新。
- 日期化验收报告只记录执行证据，不定义当前优先级。
- 已完成计划、旧评估、旧版本规格和重复截图直接删除，不再建立新的历史文档堆。
- 文档版本使用 `v0.x`；包和 Git tag 使用完整语义版本 `0.x.y`。
