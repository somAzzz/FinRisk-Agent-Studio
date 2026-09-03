# FinRisk Agent Studio v0.1 文档

文档只保留当前产品说明、长期有效的架构决策、运行指南和可复现的验收方法。阶段性计划、重复截图和已经由最终结论覆盖的迁移记录不再放在当前文档树中；需要追溯时使用 Git 历史。

## 核心文档

1. [项目全景与面试讲法](PROJECT_OVERVIEW_INTERVIEW_CN.md)：已经实现的能力、实现方式、技术取舍、演示路径和面试话术。
2. [项目状态](STATUS.md)：目标、子系统完成情况、验证基线和已知限制。
3. [路线图](ROADMAP.md)：v0.1 发布条件及 v0.2–v0.4 方向。
4. [系统架构](ARCHITECTURE.md)：产品域、服务、数据、工作流和安全边界。
5. [v0.1 规格](specs/v0.1.md)：当前版本的功能与验收契约。
6. [Pydantic AI 单一运行时 ADR](ADR_PYDANTIC_AI_RUNTIME.md)：模型边界、项目侧治理职责和部署回滚决策。
7. [版本策略](VERSIONING.md)：文档小版本、包版本和 Git tag 的对应关系。

## 使用指南

- [个人研究闭环](guides/research-cycle.md)
- [LLM Provider 配置与验收](guides/llm-provider-validation.md)

## 测试与验收

- [真实数据验收](testing/real-data-acceptance.md)
- [Research Journal 本地 LLM 验收方法](testing/research-journal-live-acceptance.md)
- [财务勾稽结果](validation/financial-reconciliation.md)
- [前端验收结果](validation/frontend-acceptance.md)
- [Research Journal 本地 LLM 验收结果](validation/research-journal-live.md)

## 运维与安全

- [Docker 镜像固定](operations/deployment/docker-image-pinning.md)
- [安全限制与已知边界](operations/security/known-limitations.md)

## 维护规则

- 当前完成状态只在 `STATUS.md` 更新。
- 未来计划只在 `ROADMAP.md` 更新。
- v0.1 的产品和技术契约只在 `specs/v0.1.md` 更新。
- 日期化验收报告只记录仍可复现的执行证据，不定义当前优先级。
- 已完成计划、逐阶段评估、旧版本规格和重复截图直接删除，由 Git 历史承担归档。
- 文档版本使用 `v0.x`；包和 Git tag 使用完整语义版本 `0.x.y`。
