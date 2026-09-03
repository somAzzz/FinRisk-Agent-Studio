# Chapter 11：建立披露文档、证据与评估合同

## 本章结果

本章先实现不依赖 PDF 库、retriever 或模型的气候披露合同。完成后，文档、候选、已验证证据、
标准映射、指标和 requirement assessment 各有独立含义，现有 FinRisk `EvidenceCandidate` 不会
被误当成最终气候证据。

前置条件：Chapter 10 的仓库边界和 provenance gate 已通过。许可未完成不阻止编写原创合同，
但仍阻止复制旧代码和词袋。

## 设计决定

1. 通用候选、气候证据、标准映射和最终 assessment 是四层对象。
2. source document、block 和原始 evidence 不可变；模型不能改写 quote。
3. requirement 状态只有 `present`、`partial`、`not_found`、`uncertain`、`not_applicable`。
4. `not_found` 是完整分析后的保守结果；任何关键阶段失败优先得到 `uncertain`。
5. 新建独立 `ClimateDisclosureWorkflowState`，不继续扩充 `FinRiskWorkflowState`。
6. `src/domains/climate/` 不能 import Pydantic AI、FastAPI、具体存储或 retriever。

## 文件变更总览

### 新建生产文件

```text
src/evidence/locators.py
src/data/disclosures/__init__.py
src/data/disclosures/contracts.py
src/disclosures/__init__.py
src/disclosures/contracts.py
src/domains/__init__.py
src/domains/climate/__init__.py
src/domains/climate/models.py
src/workflows/climate_state.py
```

### 新建测试

```text
tests/evidence/test_locators.py
tests/data/disclosures/test_contracts.py
tests/disclosures/test_contracts.py
tests/domains/climate/test_models.py
tests/workflows/test_climate_state.py
tests/architecture/test_climate_boundaries.py
```

不要为了匹配目录图创建没有消费者的 `pdf_parser.py`、Agent 或 API；它们属于后续章节。

## 11.1：SourceDocument、DocumentBlock 与 SourceLocator

`src/evidence/locators.py` 定义可复用定位原语；`data/disclosures/contracts.py` 定义摄取对象。
最低字段：

```text
DocumentRef
  document_id, source_hash, source_type, source_uri, language,
  issuer_id, reporting_period, retrieved_at

SourceLocator
  document_id, block_id, page, char_start, char_end,
  bbox, table_id, row, column, heading_path

DocumentBlock
  schema_version, block_id, document_id, order, kind,
  text, text_hash, locator, parent_block_id, ingestion_issues
```

约束：

- `char_start < char_end`，并说明 offset 相对于原始文档还是规范化 block；
- TXT 没有页码时用 `None`，禁止制造 page 1；
- bbox 必须带页面和坐标系定义；
- table cell locator 不用普通段落 offset 冒充；
- `text_hash` 从未改写的 canonical block text 计算；
- block ID 由稳定输入生成，不依赖本次 list index 或本地绝对路径。

## 11.2：Requirement 与 profile 合同

`src/disclosures/contracts.py` 只定义标准无关的结构：

```text
Requirement
  requirement_id, framework, edition, title, summary,
  source_locator, applicability_rule_ids, rubric_rule_ids,
  retrieval_hint_ids, status

FrameworkProfile
  profile_id, framework, edition, registry_version,
  requirement_ids, source_urls, content_hash, review_status

RequirementMapping
  source_requirement_id, target_requirement_id,
  relation, direction, rationale, registry_version
```

`relation` 至少区分 `exact`、`broader`、`narrower`、`related`。requirement 正文、rubric 和
retrieval hint 是不同字段；不能把关键词 query 写成标准要求本身。

## 11.3：ClimateEvidence 与映射

`src/domains/climate/models.py` 定义：

```text
ClimateEvidence
  evidence_id, document_ref, locator, quote, quote_hash,
  evidence_type, climate_topics, claim_summary,
  extractor_revision, verification_state, created_at

RequirementEvidenceMapping
  mapping_id, evidence_id, requirement_id,
  relationship: supports | partially_supports | contradicts,
  rationale, extractor_revision

VerificationDecision
  mapping_id, verdict: supported | partial | unsupported | uncertain,
  reason_codes, rationale, verifier_revision, verified_at
```

核心不变量：

- quote 必须非空并能在 locator 指向的 block 中精确复现；
- `claim_summary` 是模型概括，不能替代 quote；
- evidence 不直接嵌入某个 framework 的唯一 requirement ID；
- 一条 evidence 可以有多个 mapping，但每个 mapping 独立验证；
- unsupported mapping 不能进入肯定性聚合；
- extractor 与 verifier 的模型/版本关系在 manifest 中可见，不能虚称“独立验证”。

## 11.4：MetricObservation

指标与一般文字证据分开建模：

```text
MetricObservation
  observation_id, evidence_id, metric_type,
  raw_value, raw_unit, normalized_value, normalized_unit,
  period, scope, boundary, table_locator,
  normalization_rule_id, issues
```

要求 raw value 永远保留。单位、期间、Scope、组织边界、倍率或表头不确定时添加 issue，不猜测
normalized value。多个表格单元共同形成一个指标时，保留所有 cell locator。

## 11.5：RequirementAssessment 与 DisclosureProfile

```text
RequirementAssessment
  requirement_id, status, supporting_mapping_ids,
  contradictory_mapping_ids, issue_ids,
  applicability_trace, rubric_rule_ids, assessed_at

DisclosureProfile
  run_id, profile_id, document_ids, assessments,
  status_counts, applicable_count, completed_count,
  analysis_completion, failures, manifest_ref
```

跨字段约束：

- `present/partial` 必须至少引用一个 verified supporting mapping；
- `not_applicable` 必须有 applicability trace；
- `not_found` 不能携带 provider/retrieval/ingestion 未完成 issue；
- `uncertain` 必须说明阻断完成判断的 issue/failure；
- status counts、denominator 和 assessment 数量可独立重算。

本章只实现 schema，不实现如何得到状态；聚合器在 Chapter 15。

## 11.6：独立 workflow state

`ClimateDisclosureWorkflowState` 至少分开保存：

```text
request / manifest
documents / blocks / ingestion issues
requirements / retrieval summaries / candidates
climate evidence / mappings / verification decisions / metrics
assessments / profile / failures / review items
trace / checkpoints / status
```

不要继承 `FinRiskWorkflowState`，也不要把全部字段声明为 `Any` 或 `dict` 来逃避循环依赖。
共享 trace、run-store protocol 和时间工具可以组合使用，但业务状态必须独立版本化。

## 11.7：稳定身份与版本

为 document、block、candidate、evidence、mapping、assessment 定义 ID 规则并测试：

- 相同 canonical input 产生相同 ID；
- 文件移动不改变 document identity；
- 内容变化改变 hash/identity；
- mapping ID 同时包含 evidence 与 requirement identity；
- schema major 未知时 fail closed；
- run ID 与 evidence identity 分离，重复运行可引用同一源证据但保留不同 run manifest。

## 11.8：架构测试

`test_climate_boundaries.py` 至少检查：

- `src/domains/climate` 不 import `pydantic_ai`、`src.ai`、FastAPI、API、具体 store；
- `src/disclosures/contracts.py` 不 import retriever、Agent 或 workflow；
- `src/data/disclosures/contracts.py` 不 import PDF/OCR provider；
- workflow 可以依赖 domain/application，但 domain 不反向依赖 workflow；
- `ClimateEvidence` 不继承 `NormalizedEvidence`；
- `ClimateDisclosureWorkflowState` 不继承 `FinRiskWorkflowState`。

## 本章验收

```bash
uv run pytest -q \
  tests/evidence/test_locators.py \
  tests/data/disclosures/test_contracts.py \
  tests/disclosures/test_contracts.py \
  tests/domains/climate/test_models.py \
  tests/workflows/test_climate_state.py \
  tests/architecture/test_climate_boundaries.py
uv run ruff check src/evidence src/data/disclosures src/disclosures src/domains/climate
uv run mypy src
```

- [ ] 所有持久化合同有 schema version。
- [ ] quote/span/hash 和跨引用不变量由代码检查。
- [ ] 五状态没有和 workflow success/failure 混用。
- [ ] 通用 candidate 不会自动成为 ClimateEvidence。
- [ ] 独立 climate state 不扩充现有大状态。
- [ ] domain 无模型、I/O、API 和具体检索依赖。

本章建议提交：

```text
ch11: establish climate disclosure evidence contracts
```
