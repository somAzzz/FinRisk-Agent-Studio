# 气候披露迁移实验

> 状态：未进入 FinRisk 当前产品路线。本目录是条件式架构推演，不是 backlog、
> 当前能力清单或发布承诺。

这条路线探讨如何将 `llm_tcfd` 研究资产选择性迁入 FinRisk，同时保持单一 runtime、
可回源证据、确定性 assessment 与可回滚发布。

## 启动门

在任何 Chapter 11–16 工作前，[Chapter 10](10-integration-boundaries.md) 必须有可验证的通过记录：

- 一个明确的 product/engineering owner；
- 用户、产品范围和成功指标；
- 源代码、词表、标准文本与测试资产的许可结论；
- 真实报告的数据授权、provider、保留和脱敏策略；
- 固定完整 source revision 的 provenance manifest；
- 明确禁止 FinRisk 在运行时 import 或读取 TCFD 工作区。

未通过时，不创建生产 climate 模块，不复制词表，不使用未授权真实报告。

## 章节路线

| 章节 | 迁移问题 | 状态 |
| --- | --- | --- |
| [10. Integration Boundaries](10-integration-boundaries.md) | owner、许可、数据、provenance 和仓库边界 | 重启门 |
| [11. Evidence Contracts](11-evidence-contracts.md) | document、locator、evidence、mapping 和 assessment 合同 | 条件式推演 |
| [12. Document Ingestion](12-document-ingestion.md) | 可回源的多市场文档摄取 | 条件式推演 |
| [13. Registry & Retrieval](13-registry-retrieval.md) | 版本化 requirement registry 与混合召回 | 条件式推演 |
| [14. Climate Agents](14-climate-agents.md) | typed extractor/verifier 与确定性 locator/metric gate | 条件式推演 |
| [15. Assessment & Product](15-assessment-product.md) | 确定性五状态聚合、API、审核与 UI | 条件式推演 |
| [16. Shadow & Cutover](16-shadow-cutover.md) | 分层 eval、shadow、release gate 和 rollback | 条件式推演 |

详细源资产映射和证据链见[迁移总图](MIGRATION_MAP.md)。

## 参考基线

```text
FinRisk historical review: 558e276f7880b081f64c4fecabdadc7212e3db59
TCFD source baseline:      4ef1c0f49853d2821dbf1ead73259d65475ca8d3
```

实际重启时必须使用当时的完整 SHA 和重新审核结论，不应直接复制历史基线。

## 实施顺序

```text
M0 restart / ownership / license / data / provenance
  -> M1 domain contracts
  -> M2 traceable ingestion
  -> M3 registry and retrieval
  -> M4 typed extraction and verification
  -> M5 deterministic assessment and product integration
  -> M6 layered eval, shadow, release and rollback
```

每一阶段都必须在下一阶段开始前通过自己的机械门。不把合同、词表、Agent、API、UI 和
真实数据塞进一个大提交。
