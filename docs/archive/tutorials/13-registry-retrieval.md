# Chapter 13：Requirement Registry 与混合候选召回

## 本章结果

本章建立经过版本审核的披露要求 registry，并把 TCFD A/B 共现算法改造为多个召回通道之一。
完成后，系统从 requirement 出发查询文档，保留每个通道的命中 provenance；无候选不会提前变成
`not_found`。

前置条件：Chapter 12 能稳定产生带 locator 的 blocks，Chapter 10 的词表许可门已经通过；若词表
仍 blocked，可以用小型 synthetic lexicon 完成本章代码和测试，但不能发布真实词表 profile。

## 设计决定

1. 首个闭环使用 TCFD 11 项兼容 profile；IFRS S2 是长期主 profile。
2. requirement 正文、rubric、applicability 和 retrieval hints 分开版本化。
3. A/B 共现是 `lexical` channel，不是证据或 assessment gate。
4. 不直接相加 BM25、embedding、共现等不可比 raw score。
5. retrieval failure、quota 和 truncation 全部进入 summary。
6. registry 更新生成新版本，不原地改变历史 run 的含义。

## 文件变更总览

### 新建 registry

```text
src/disclosures/registry.py
src/disclosures/mapping.py
config/disclosures/frameworks/tcfd/<edition>/profile.yaml
config/disclosures/frameworks/tcfd/<edition>/requirements.yaml
config/disclosures/frameworks/ifrs_s2/<edition>/...
config/disclosures/frameworks/esrs_e1/<edition>/...
tests/disclosures/test_registry.py
tests/disclosures/test_mapping.py
```

IFRS S2/ESRS 目录只有在有真实、审核过的内容时创建；不要提交空 profile 让 loader 误判为支持。

### 新建 retrieval

```text
src/retrieval/__init__.py
src/retrieval/contracts.py
src/retrieval/climate/__init__.py
src/retrieval/climate/lexical.py
src/retrieval/climate/section.py
src/retrieval/climate/semantic.py
src/retrieval/climate/fusion.py
config/climate/lexicons/<version>/manifest.yaml
tests/retrieval/climate/
```

## 13.1：生产 registry loader

loader 必须验证：

- framework、edition、registry version、source URL/locator 和 content hash；
- requirement ID 唯一且 profile 引用全部存在；
- TCFD 11 项数量和四支柱归属正确；
- rubric/applicability/hint ID 不悬空；
- mapping 两端存在、方向明确、关系类型有效；
- `draft`、`withdrawn`、`unreviewed` profile 默认拒绝生产加载；
- unknown major schema fail closed。

不要把官方材料的大段原文复制进仓库。保存必要的短标题/摘要、定位和 hash，并让 Standards
Reviewer 确认没有扩大或偷换要求含义。

## 13.2：TCFD 与 IFRS S2/ESRS 映射

同一 `ClimateEvidence` 通过 mapping 连接多个 framework。跨标准映射必须回答：

- 从哪个 edition 到哪个 edition；
- 是 exact、broader、narrower 还是 related；
- 映射方向是否可逆；
- 哪些额外条件无法从源 requirement 推出；
- 谁在何时审核。

TCFD 的肯定结果不能直接填充完整 IFRS S2 或 ESRS E1。未实现的 profile 显示 unsupported，不能
显示 `not_found`。

## 13.3：定义 retrieval 合同

```text
RetrievalQuery
  query_id, requirement_id, hint_id, languages,
  channels, top_k, context_budget, revision

CandidateHit
  candidate_id, block_id, channel, raw_score, rank,
  hit_spans, matched_terms, query_id, producer_revision

RetrievalSummary
  requirement_id, requested_channels, completed_channels,
  failed_channels, candidate_count, truncated_count,
  token/character budget, issues
```

candidate ID 去重后仍保留所有 channel hit。raw score 只在本通道解释；fusion 使用 rank-based 或
经过校准的策略，并记录 fusion revision。

## 13.4：移植共现算法

旧算法可复用词边界和窗口思想，但必须修复/改变：

- 固定 ±30 字只作为可配置 signal；
- 单句窗口支持中英文终止符和 block 边界；
- 搜索所有有效 B 命中，而不是每个 A 只取第一个；
- 明确重叠词、最长匹配、空字符串、Unicode NFKC/case-folding 策略；
- 不用“A 后十字出现公司”作为普遍真理；若保留，只是版本化 heuristic；
- 输出 `CandidateHit` 和精确 hit span，不输出最终计数结论；
- dimension 词表只是 retrieval metadata，不冒充 TCFD pillars。

旧 parity fixture 用于解释行为变化，不要求新算法复制已知缺陷。每个 deliberate difference 写入
provenance 的 `port_changes`。

## 13.5：其他通道

最低建议通道：

| 通道 | 目的 | 主要风险 |
| --- | --- | --- |
| section/heading | 利用治理、风险、指标等结构 | 标题缺失或误识别 |
| lexical/BM25 | 可解释、低成本召回 | 同义表达漏召回 |
| A/B co-occurrence | 精确抓取气候+风险/财务语境 | 固定窗口和词义误判 |
| semantic | 跨语言/同义表达召回 | 模型版本、成本、漂移 |

通道关闭或失败时仍可运行，但 summary 必须记录 completeness。semantic index key 包含 block hash、
embedding model/revision 和 normalization config，不能跨不同文档或版本误用缓存。

## 13.6：上下文组装

候选交给 Agent 前，按 block kind 组装：

- 段落：标题路径、相邻段和精确 span；
- 表格：表头、单位、行列、脚注和相邻说明；
- 跨页：保留每页/cell locator；
- OCR：附质量 issue，不把修正文当原文；
- 多 requirement：共享 block，但每个 query 的命中理由独立。

上下文预算截断发生时记录被删 blocks/span 和原因。不能在 Agent 失败后悄悄扩展到整份报告。

## 13.7：retrieval eval

冻结的 gold 单位是 `(document, requirement, relevant block/span)`。报告：

- Recall@k、MRR；
- 每通道独立贡献和 ablation；
- 按 pillar、requirement、语言、市场、格式、OCR/table 切片；
- candidate 数、context 大小、耗时、失败和截断；
- 最差关键切片，不只报总体平均。

threshold 必须基于 dev set；test 不参与词表、query、fusion 或 top-k 调整。

## 本章验收

```bash
uv run pytest -q tests/disclosures tests/retrieval/climate
uv run ruff check src/disclosures src/retrieval tests/disclosures tests/retrieval
uv run mypy src
uv run python eval/climate_retrieval/run.py --dataset synthetic
```

- [ ] 生产 profile 只能加载已审核 registry。
- [ ] TCFD 11 项完整，跨框架映射有 edition、方向和关系类型。
- [ ] 每个 candidate 保留 query、channel、rank、span 和 revision。
- [ ] A/B 共现关闭后系统仍能运行。
- [ ] 通道失败或无候选没有直接生成 `not_found`。
- [ ] retrieval eval 无公司/年份泄漏。

本章建议提交：

```text
ch13: add reviewed requirements and hybrid climate retrieval
```
