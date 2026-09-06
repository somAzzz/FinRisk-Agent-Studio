# Chapter 10：气候披露方案的仓库边界与重启条件

> 路线状态：未进入当前产品路线。本章是
> [气候迁移实验](README.md)的启动门，不是对当前 `main` 的实施指令。

> 当前状态：本章属于归档架构推演，不是 FinRisk 当前产品路线。`docs/README.md` 已将
> TCFD 气候披露合并方案标记为“已退出当前路线”，当前仓库也没有
> `src/domains/climate/`、`src/retrieval/climate/` 或 climate workflow。

## 本章结果

本章不要求现在创建气候业务代码。它回答的是：如果未来重新批准 TCFD/气候披露工作包，如何在
不破坏当前 Pydantic AI、evidence、run-store 和 product boundaries 的前提下启动迁移。

完成本章后，你应能区分：

- 当前仓库事实；
- 历史来源基线；
- 尚未批准的未来迁移产物；
- 代码许可、数据授权和运行时依赖三类不同问题。

## 10.1：当前仓库事实

本文复核的 FinRisk commit：

```text
558e276f7880b081f64c4fecabdadc7212e3db59
```

历史计划记录的 TCFD source baseline：

```text
4ef1c0f49853d2821dbf1ead73259d65475ca8d3
```

第二个 SHA 只是归档计划中的参考来源。本次复核没有重新检查外部工作区，因此不能把它描述为
当前可用、许可已确认或工作树干净。

当前 FinRisk 已经具备可复用的横切能力：

- `src/ai/model_factory.py` 的唯一 provider/model 构造；
- typed Agents、toolsets 和 Pydantic Graph；
- evidence、claim、source quality 与 graph provenance；
- run/message store、conversation resume、trace、approval 和 memory guardrails；
- API auth、rate limit、URL guard 和 redaction；
- 离线 golden cases 与 live provider acceptance。

如果未来增加 climate domain，应复用这些边界，不创建 `climate_model_factory.py`、私有 OpenAI
client、第二套 message store 或第二套 Agent runtime。

## 10.2：当前不存在的产物

旧版教程把以下路径写成“本章新建”，但它们目前并不存在：

```text
docs/migration/tcfd-provenance.yaml
docs/adr/00XX-climate-disclosure-repository-boundary.md
tests/architecture/test_climate_repository_boundary.py
src/domains/climate/
src/retrieval/climate/
src/ai/agents/climate/
```

这不是当前 v0.1 缺陷。`docs/ROADMAP.md` 的 v0.1–v0.4 也没有承诺气候披露产品线。除非 owner
重新批准范围、许可、数据政策和维护责任，否则不要为了让归档教程“通过”而创建空目录或占位
manifest。

## 10.3：未来重启时的第一道门

重启迁移前必须先形成一份新的、当前有效的 decision record，至少回答：

```text
为什么现在进入产品路线
谁是 domain owner
目标用户和可验收结果是什么
与现有 RiskType="climate" 有何区别
来源代码和数据的许可证是什么
哪些文档可以发送给外部模型
哪些 artifact 可以提交 Git
预算、存储和删除责任由谁承担
如何回滚而不影响现有 FinRisk 数据
```

只有 decision 被接受后，才创建 provenance manifest 和 architecture test。归档教程本身不能代替
产品范围批准或许可证判断。

## 10.4：Provenance manifest 的建议合同

若迁移获批，每个被移植或改写的 artifact 应单独记录：

```text
artifact_id
kind: code | test | lexicon | eval | document
source_repository
source_commit
source_path
source_sha256
declared_license
license_evidence
destination_path
destination_commit
port_changes
review_status
reviewer
reviewed_at
```

规则：

- commit 使用完整 SHA；
- code、data、词表和文档分别判断许可；
- `port_changes` 写清语义变化，不能只写 `refactor`；
- destination 尚未提交时保持 `null`；
- 一个 source 生成多个目标文件时使用不同 artifact ID；
- 新 revision 追加记录，不覆盖旧 provenance；
- manifest 只用于审核，不成为运行时查找外部仓库的配置。

## 10.5：许可与数据授权是两道门

历史计划记录过以下未决问题：

- TCFD README 曾声称 MIT，但当时没有 tracked `LICENSE`；
- FinRisk 项目代码许可证没有在该计划中得到 owner 级确认；
- 词袋的来源、生成过程和再分发权需单独核对；
- 真实年报可用于本地分析，不自动意味着可提交、公开或发送到外部 endpoint。

这些结论必须在重启时重新核实。未确认项保持 `review_status: blocked`，不能从相同 Git owner、
公开 URL 或 README 一句话推导出完整授权。

数据 inventory 至少记录：

| 字段 | 含义 |
| --- | --- |
| source | SEC、交易所、公司网站、本地语料或 synthetic |
| market/language | 市场与语言 |
| format | HTML、TXT、PDF、OCR、table |
| contains_private_text | 是否含受限或个人数据 |
| may_commit_fixture | 是否可进入 Git |
| may_send_external_model | 是否可发送给外部 provider |
| retention | 原文、trace、模型请求保留期 |
| owner | 谁批准用途与删除 |

## 10.6：未来 architecture boundary

如果迁移获批，architecture test 应精确禁止运行时耦合：

- `src/` 不 import `tcfd_extractor`；
- `pyproject.toml` 不加入外部工作区的 editable/path dependency；
- 生产代码不出现某台机器的绝对路径；
- 配置不读取 `TCFD_REPO_PATH` 来动态注入模块；
- provenance 文档可以提及来源仓库，但 runtime 不读取它来执行外部代码。

测试不能简单禁止字符串 `TCFD` 或 `climate`，因为当前风险分类和正常文档会合法使用这些词。

目标依赖方向应是：

```text
external research repository
  -- reviewed port with provenance -->
FinRisk-owned climate implementation
  -> existing evidence / AI / workflow / API boundaries
```

FinRisk 不能在运行时反向依赖研究仓库。

## 10.7：候选资产如何分类

未来 inventory 应分为：

| 分类 | 处理方式 |
| --- | --- |
| 直接复用 FinRisk | model factory、SEC/XBRL、trace、approval、run store |
| 审核后改写 | chunking 思路、lexical/co-occurrence 召回、eval 原则 |
| 按 FinRisk 合同重构 | evidence、requirement mapping、workflow state |
| 留在研究仓库 | clustering、t-SNE、旧 HTML、Markdown 中间合同 |

不能说明目标合同和维护 owner 的文件不迁移。所谓“移植”应是进入 FinRisk 后由 FinRisk 单独维护，
不是长期同步两个工作区。

## 10.8：当前验收与未来验收

### 当前只需确认归档状态准确

```bash
rg -n "tcfd_extractor|TCFD_REPO_PATH|frequency_analyzer" \
  src pyproject.toml
find src -maxdepth 3 -type d | rg "climate|tcfd"
git diff --check
```

当前期望：生产代码和依赖没有外部 TCFD runtime coupling；不存在气候业务目录也是正常结果。

### 未来迁移获批后才增加

```text
provenance manifest schema test
license/data review gate
cross-repository dependency architecture test
synthetic climate contract fixtures
```

- [ ] 当前文档没有把归档计划冒充产品路线。
- [ ] 历史 source SHA 没有被写成重新验证过的事实。
- [ ] 未经批准没有创建 climate 占位代码。
- [ ] 若未来重启，先完成 owner、license、data 和 provenance gate。
- [ ] 未来 climate Agent 复用唯一 `src.ai` runtime。
- [ ] FinRisk 在外部研究仓库不存在时仍可安装、测试和运行。

## 当前结论

Chapter 10 的 repository-boundary 原则仍然合理，但迁移本身目前不在路线图中。最适合当前仓库
状态的做法是保留这份可审计的重启指南，而不是执行旧版文件清单。当前产品范围和后续优先级始终
以 `docs/STATUS.md`、`docs/ROADMAP.md` 和 `docs/specs/v0.1.md` 为准。
