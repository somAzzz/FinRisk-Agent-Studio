# Chapter 10：固定跨仓库边界与迁移来源

## 本章结果

本章不搬代码，先把 `llm_tcfd` 研究仓库与 FinRisk 生产仓库的职责、版本、许可、数据边界和
回滚方式固定下来。完成后，后续每个移植项都有可核对的 source commit、路径、hash 和语义变化，
FinRisk 也不会在运行时依赖另一个工作区。

这是气候披露迁移线的第一章。Chapter 6–9 已经完成 Pydantic AI runtime 重构；本章从完成后的
FinRisk 代码基线开始，不重复创建 model factory、tool loop 或第二套 Agent runtime。

## 前置基线

建议以以下代码状态开始练习：

```text
FinRisk code baseline: 145e34b2e3a39cf78f78a226f20108c97d30962d
TCFD source baseline:  4ef1c0f49853d2821dbf1ead73259d65475ca8d3
```

先分别确认：

```bash
git -C /path/to/fintext_llm status --short
git -C /path/to/fintext_llm rev-parse HEAD
git -C /path/to/frequency_analyzer status --short
git -C /path/to/frequency_analyzer rev-parse HEAD
```

实际练习使用更新 commit 时，以自己的完整 SHA 为准，不复制上面的历史值冒充来源。

## 设计决定

1. FinRisk 是唯一生产实现，TCFD 仓库是 research/benchmark predecessor。
2. 不使用 unrelated-history merge、submodule、editable install 或相对路径建立运行时依赖。
3. 选择性移植记录 provenance；进入 FinRisk 后由 FinRisk 维护生产版本。
4. 许可和数据授权是迁移硬门，不是 README 最后一段的补充说明。
5. 本章只建立边界和检查，不提前创建空的完整气候目录树。

## 文件变更总览

### FinRisk 新建

| 文件 | 职责 |
| --- | --- |
| `docs/migration/tcfd-provenance.yaml` | 记录每个代码、测试、词表和 eval 资产的来源与目标 |
| `docs/adr/00XX-climate-disclosure-repository-boundary.md` | 固定仓库所有权、依赖方向和回滚决策 |
| `tests/architecture/test_climate_repository_boundary.py` | 防止生产代码 import `tcfd_extractor` 或引用本地 TCFD 路径 |

### FinRisk 修改

| 文件 | 修改内容 |
| --- | --- |
| `docs/migration/tcfd-integration-plan.md` | 填入实际 source/destination baseline 与决策链接 |
| `docs/README.md` | 将合并方案和 ADR 纳入文档入口 |
| `.gitignore` | 明确真实年报、临时移植目录和本地 eval 输出不得进入 Git |

本章不修改 `src/`，也不把 `docs/word-bags/` 复制进 FinRisk。

## 10.1：定义 provenance 记录

每个移植项至少包含：

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

要求：

- commit 使用完整 SHA；
- code 与 data 分开记录许可；
- `port_changes` 说明语义改变，不只写“refactor”；
- destination 尚未提交时保持 `null`，不能猜未来 SHA；
- 同一 source 生成多个目标文件时使用不同 artifact ID；
- 文件更新生成新记录或新 revision，不覆写旧来源历史。

provenance manifest 是审核材料，不是运行时从 TCFD 仓库加载代码的配置。

## 10.2：先解决许可硬门

当前已知状态：

- TCFD README 声称 MIT，但仓库没有 tracked `LICENSE`；
- FinRisk README 说明 Yahoo Finance 数据为 ODC-BY，但没有明确项目代码许可证；
- TCFD 词袋还需要单独核对来源、生成过程和可再分发权。

因此练习允许先填写 `review_status: blocked`，但在许可确认前不得：

- 复制 TCFD 源文件或大段代码；
- 把词袋导入 FinRisk `config/`；
- 把真实年报片段提交为 fixture；
- 在公开文档里把来源不明数据标为 MIT。

许可决定需要仓库所有者完成。教程不能代替所有者选择许可证，也不能从 Git remote 相同推断
所有数据都有相同授权。

## 10.3：建立数据 inventory

为候选数据集逐项记录：

| 字段 | 含义 |
| --- | --- |
| source | SEC、交易所、公司网站、本地语料或 synthetic |
| market/language | 美国/中国等市场及语言 |
| format | HTML、TXT、PDF、OCR、table |
| contains_private_text | 是否含未公开、受限或个人数据 |
| may_commit_fixture | 能否进入 Git |
| may_send_external_model | 能否发送到外部 endpoint |
| retention | 原文、trace、模型请求的保留期 |
| owner | 谁批准用途与删除 |

默认策略应保守：本地年报可以用于经批准的本地测试，不等于可以提交、公开或发送给外部模型。

## 10.4：自动禁止跨仓库运行时依赖

`test_climate_repository_boundary.py` 用 AST 和源码扫描至少断言：

- `src/` 不 import `tcfd_extractor`；
- `pyproject.toml` 不出现 `frequency-analyzer`、本地 Git URL 或 editable path dependency；
- `src/`、`config/` 不包含 `/home/.../frequency_analyzer` 绝对路径；
- 生产配置不读取 `TCFD_REPO_PATH` 一类环境变量；
- provenance 文档可以包含来源仓库标识，但不会被 runtime 当模块目录使用。

测试不应禁止合法的领域字符串，例如报告中出现“TCFD”；它检查的是依赖和路径，不是普通文本。

## 10.5：建立移植 inventory

把候选项分为四类：

| 分类 | 示例 | 本章决定 |
| --- | --- | --- |
| 复用 FinRisk | model factory、trace、approval、SEC/XBRL | 保留唯一生产所有者 |
| 改造移植 | SmartChunker、共现召回、词表、eval 原则 | 后续章节逐项进入 provenance |
| 完全重构 | evidence、requirement mapping、workflow state | 不从旧类型继承错误语义 |
| 留在研究仓库 | clustering、t-SNE、旧 HTML、Markdown 中间合同 | 不创建生产目标路径 |

如果无法说明某个文件服务哪个目标合同，就不迁移它。

## 10.6：本章审核

本章对应合并门 `M0` 和 V2 审核门 `G0`。审核者应独立确认：

- 两个基线 commit 存在且工作树状态已记录；
- provenance schema 可表示代码、数据、测试和派生资产；
- 许可未确认的资产明确 blocked；
- data inventory 区分提交、外传和本地使用；
- architecture test 能抓住 import、path dependency 和绝对路径三类违规；
- 没有为了“以后会用”复制整个旧目录。

## 本章验收

```bash
uv run pytest -q tests/architecture/test_climate_repository_boundary.py
uv run ruff check tests/architecture/test_climate_repository_boundary.py
git diff --check
```

- [ ] FinRisk 和 TCFD 基线使用完整 SHA。
- [ ] 每个待移植资产有 provenance 条目或明确不迁移理由。
- [ ] 许可和真实数据策略有 owner；未知项保持 blocked。
- [ ] FinRisk 在 TCFD 仓库不存在时仍可安装、测试和启动。
- [ ] 本章没有引入气候业务占位代码或第二套 runtime。

本章建议提交：

```text
ch10: fix climate migration ownership and provenance
```
