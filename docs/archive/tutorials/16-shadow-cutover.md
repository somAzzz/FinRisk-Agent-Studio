# Chapter 16：分层 Eval、Shadow Run 与受控切换

## 本章结果

本章用冻结数据分别评估 ingestion、retrieval、evidence、verification 和 assessment，随后让旧 TCFD
共现流程与新 FinRisk climate workflow 并行运行。只有质量、失败语义、数据治理和回滚门全部通过，
FinRisk 才成为默认入口，TCFD 仓库才正式收口为 research predecessor。

前置条件：Chapter 15 的新入口默认关闭，完整 artifacts、trace 和 rollback path 可用。

## 设计决定

1. 不用一个总 accuracy 掩盖不同阶段问题。
2. gold 单位是 requirement + source span + verdict/status，不是关键词列表。
3. train/dev/test 按公司和年份分组，避免相邻报告泄漏。
4. 旧共现结果与新五状态 profile 不直接比较单一分数。
5. shadow 不写生产结论，不触发外部通知或写操作。
6. 发布门先看 P0/P1 和机械正确性，再看模型质量阈值。

## 文件变更总览

### 新建 eval

```text
eval/climate_disclosure/
  README.md
  models.py
  datasets/
    synthetic.jsonl
    manifest.yaml
  retrieval.py
  evidence.py
  verification.py
  assessment.py
  shadow.py
  release_gate.py
tests/eval/climate_disclosure/
docs/validation/climate-disclosure-shadow.md
docs/operations/climate-disclosure-runbook.md
```

真实报告和 live 输出默认放在 ignored artifact root，不放入 `eval/.../datasets`。

### 修改

- CI：增加离线 climate contract/eval gate；
- `docs/STATUS.md`：只按实际 gate 更新完成状态；
- `docs/ROADMAP.md`：删除已完成阶段，记录未解决切片；
- TCFD README：切换后标记 research/benchmark predecessor；
- provenance manifest：填写最终 destination commit 和 review 结论。

## 16.1：数据集和标注

每个 gold case 至少包含：

```text
case_id
document_group_id / issuer_id / reporting_period
input_artifact refs
framework/profile/registry version
expected relevant blocks/spans
expected evidence types
expected requirement mappings/verdicts
expected assessment or allowed statuses
expected failures/issues
tags
annotation revision/review status
```

样本覆盖中英文、SEC/A 股、TXT/HTML/PDF/OCR/table、明确/部分/无披露、输入不完整、冲突和
不适用。synthetic seed 可进入 Git；真实报告只保存 hash、授权状态和受控位置。

至少对一部分样本双人标注并记录一致性、分歧和仲裁。没有领域审核的 seed 只能称回归集，不能称
权威 gold 或用于发布宣传。

## 16.2：防止数据泄漏

- 同一 issuer 的相邻年份进入同一 split；
- 同一模板、修订报告和派生片段不跨 split；
- test 不参与 prompt、词表、query、fusion、threshold 和 rubric 调整；
- TCFD 历史输出若用于生成 case，记录 lineage，避免 prediction 伪装成人工 gold；
- error analysis 只在 dev 迭代；最终 test 运行生成不可覆盖报告。

## 16.3：分层指标

| 层 | 最低指标 |
| --- | --- |
| ingestion | page/block coverage、locator correctness、issue recall |
| retrieval | Recall@k、MRR、channel contribution、truncation |
| evidence | span precision/recall、type accuracy、exact grounding |
| verification | supported/partial/unsupported/uncertain confusion matrix |
| metrics | raw value/unit/period/scope exactness、normalization error |
| assessment | 五状态 confusion matrix、coverage、abstention/uncertain |
| reliability | provider/schema/stage failure rate、resume correctness |
| operations | latency、requests/tokens、cost、artifact/trace completeness |

所有结果按 requirement、pillar、市场、语言、行业、格式和输入质量切片。总体平均不能掩盖关键
requirement 的最差表现。

## 16.4：机械发布硬门

以下项目必须 100%：

1. 发布 artifacts 通过声明 schema；
2. `present/partial` 全部能追到 verified quote/span；
3. quote 与 source block/hash 完全一致；
4. 每个输入 item 守恒为 success、structured failure 或 pending review；
5. manifest 唯一确定 input、code、registry、model、prompt 和 config；
6. 关键失败不映射为 `not_found`；
7. 未审核 registry/profile 不进入生产；
8. feature flag/部署回滚演练成功；
9. 真实数据没有违反提交、外传或保留政策。

任一硬门失败直接阻断，不用较高平均 F1 抵消。

## 16.5：shadow runner

shadow 使用同一输入 manifest 并分别调用：

```text
legacy TCFD research pipeline
  -> co-occurrence candidates / relevance records / failures

new FinRisk climate pipeline
  -> requirement candidates / verified evidence / assessments / failures
```

比较：

- 旧 A/B channel 对新 retrieval 的独立召回贡献；
- 旧 relevant context 是否成为 verified evidence、被拒绝或映射不同 requirement；
- 新系统发现的非共现证据；
- false positive/negative、uncertain 和 failure；
- latency、tokens、review load 和 cost。

不要比较旧“相关率”和新“披露 coverage”并得出升降结论，它们的分母与语义不同。

## 16.6：错误分类和 go/no-go

每次 shadow review 将问题分为：

- P0：数据泄漏、证据伪造、破坏性写入、不可回滚；
- P1：错误标准映射、肯定结论无证据、失败变 not_found、test 泄漏；
- P2：局部召回、性能、可用性问题，有安全绕行；
- P3：命名、诊断、非关键改进。

有 P0/P1 时 no-go。P2 conditional pass 必须有 owner、期限和不影响正确性的证据。

## 16.7：beta 与默认切换

建议顺序：

```text
internal synthetic
  -> approved local real-data shadow
  -> reviewer-only beta
  -> selected users / markets
  -> default climate entry
  -> legacy production claim removal
```

每一步固定观察窗口和回滚触发条件。切换默认入口前，Engineering、Standards、Data/Privacy、
Evaluation 和 Release owner 分别签字。

## 16.8：回滚演练

演练至少验证：

- 关闭 climate feature flag；
- 部署上一个已验证 revision；
- 新 artifacts 保留且不会被旧 reader 破坏；
- in-flight run 的 drain/cancel/resume 策略；
- registry/schema 不兼容时 fail closed；
- review audit 不丢失；
- rollback 不恢复第二套 LLM runtime。

## 16.9：TCFD 研究仓库收口

切换后 TCFD 仓库继续保留：

- 词表研究和来源历史；
- 共现、聚类和历史统计复现；
- frozen benchmark/gold annotation lineage；
- 被移植算法的 source commit。

它不再维护生产 runtime、API 或前端。旧 CLI 的归档需等历史导出、用户迁移和复现需求完成，不能
因 FinRisk beta 上线立即删除。

## 本章验收

```bash
uv run pytest -q tests/eval/climate_disclosure
uv run python eval/climate_disclosure/release_gate.py --dataset synthetic
uv run pytest -q
cd frontend && npm test && npm run build
```

真实数据和 provider 经批准后再运行：

```bash
uv run python eval/climate_disclosure/shadow.py --manifest <approved-manifest>
```

- [ ] gold lineage、split、review status 和数据授权可审计。
- [ ] 五层指标、失败、uncertain、成本和最差切片同时报告。
- [ ] 所有机械硬门通过且无 P0/P1。
- [ ] shadow 没有比较不可等价的旧/新单一分数。
- [ ] beta、默认切换和回滚均有签字与演练证据。
- [ ] TCFD 仓库的研究职责和旧 CLI 生命周期已文档化。

本章建议提交：

```text
ch16: validate shadow and cut over climate disclosure workflow
```
