# Chapter 12：统一文档摄取与可回源定位

> 路线状态：条件式迁移实验，尚未在 FinRisk 实施。文件清单表示未来目标，
> 不表示当前仓库已存在这些模块。

## 本章结果

本章把 SEC HTML、普通 TXT 和 A 股年报输入转换为 Chapter 11 的 `DocumentBlock`，并保证清洗、
切分和表格处理后仍能回到原始来源。PDF/OCR 可以分步加入，但任何未支持或失败的页面必须形成
结构化 issue，不能静默消失。

前置条件：Chapter 11 的 document、block、locator 和 ingestion issue 合同已冻结。

## 设计决定

1. adapter 负责来源差异，downstream 只消费统一 blocks。
2. `SmartChunker` 只复用边界算法和测试思想，不直接返回裸字符串。
3. 清洗后的文本必须保留原文坐标映射或独立 canonical-source 说明。
4. SEC climate disclosure 不能只读取 Item 1A。
5. 文件名是 metadata hint，不是 issuer/document canonical identity。
6. ingestion completeness 是最终 assessment 的输入，不能只写日志。

## 文件变更总览

### 新建

```text
src/data/disclosures/text_parser.py
src/data/disclosures/sec_adapter.py
src/data/disclosures/ashare_adapter.py
src/data/disclosures/chunking.py
src/data/disclosures/pdf_parser.py          # 只在本章 PDF 波次实施时创建
tests/data/disclosures/test_text_parser.py
tests/data/disclosures/test_sec_adapter.py
tests/data/disclosures/test_ashare_adapter.py
tests/data/disclosures/test_chunking.py
tests/data/disclosures/test_pdf_parser.py    # 同上
tests/fixtures/disclosures/synthetic/
```

### 修改

| 文件 | 修改内容 |
| --- | --- |
| `src/data/filing_fetcher.py` | 暴露完整 filing/source metadata，不改变现有风险工作流默认行为 |
| `src/data/sec_sections.py` | 允许 adapter 获取多 section 和原始定位，不只消费 Item 1A |
| `docs/migration/tcfd-provenance.yaml` | 记录 SmartChunker 算法/测试的移植来源与变化 |

## 12.1：定义 adapter protocol

统一入口表达为：

```text
DisclosureSourceAdapter.ingest(request)
  -> IngestionResult(document, blocks, issues, completeness)
```

请求应显式包含来源、issuer hint、reporting period、语言/编码 hint 和允许的 OCR 策略。结果必须
守恒：已发现页面/section/block 要么成功输出，要么对应结构化 issue。

adapter 不调用 LLM，不做 requirement 分类，也不判断文本是否“气候相关”。

## 12.2：TXT parser

TXT 路径先建立最小可靠闭环：

- 检测 UTF-8/UTF-8-SIG 和允许的中文编码；无法确定时失败，不用 replacement character 静默吞错；
- 保留原始 byte hash 与 canonical text hash；
- 识别空文档、异常控制字符、大量 OCR 噪声和重复页眉；
- 标题/段落分块后保存原始 offset；
- 不删除财务报表章节。旧 `annual_report_cleaner.py` 的截断行为不得移植；
- 没有页码时 locator page 为 `None`。

测试包括中文、英文、中英混合、CRLF、BOM、空行、超长段落、乱码和只有空白的文件。

## 12.3：改造 SmartChunker

从 TCFD `src/tcfd_extractor/chunker.py` 复用：

- 中英文标题识别；
- 句子、分句和硬边界顺序；
- target soft limit 与 max hard limit；
- 不丢非空白源内容的性质。

必须改变：

- 输入是带 locator 的 block，不是普通字符串；
- 输出是 child `DocumentBlock`，保存 parent ID 和 source span；
- 长表格不按普通句号切分；
- injected tokenizer length function 的 revision 进入 manifest；
- 合并/切分后可以重建 canonical text，或明确记录被规范化的空白差异。

property test 应生成不同长度和边界组合，验证硬上限、顺序、覆盖和无重叠/有意 overlap 规则。

## 12.4：SEC adapter

复用现有 `SECClient`、`FilingFetcher`、ticker/CIK resolver 和 section parser，但改变业务范围：

- 输入允许 10-K、10-Q、20-F 和指定附件；
- 获取完整 filing 和 section map；
- 保留 accession、form、filing/report date、URL、CIK；
- section 名称进入 heading path，不把 section 名当 quote；
- climate retrieval 可以覆盖 Business、Risk Factors、MD&A、治理、环境/可持续相关附件；
- 现有 `FilingRiskExtractorStep` 继续使用它自己的 Item 1A 路径，直到单独迁移，不被本章破坏。

使用 fake SEC client 做默认测试；真实 EDGAR 测试保持 integration marker。

## 12.5：A-share adapter

旧 `AnnualReportSampler` 和 filename parser 提供数据发现经验，但需重设合同：

- directory/year 只用于发现；
- filename 解析得到的是 `IssuerHint`，必须可被 metadata/resolver 修正；
- document ID 使用内容 hash + 已验证 issuer/report period，不依赖绝对路径；
- 采样接收 seed，并输出 sample manifest；
- 重复报告、修订版、同名公司和格式异常形成可审核结果；
- 本地 `/home/.../A股年报` 只能出现在用户配置/运行参数，不能写入生产默认值和测试。

## 12.6：PDF、OCR 与表格波次

PDF 支持可以晚于 TXT/HTML，但必须提前固定失败语义：

| 情况 | 结果 |
| --- | --- |
| 原生文本页 | text blocks + page/bbox locator |
| 扫描页且允许 OCR | OCR block + engine/revision/quality issue |
| 扫描页但 OCR 禁止 | blocking ingestion issue |
| 加密/损坏 PDF | document failure，不生成空成功 |
| 表格可解析 | table/cell blocks + header/unit/footnote locator |
| 跨页或结构不确定 | blocks + uncertainty issue，不猜合并关系 |

不要把整页 OCR 文本伪装成精确 cell，也不要因 PDF 库返回空字符串就认定企业没有披露。

## 12.7：完整性与 checkpoint

每次 ingestion 输出：

- expected/discovered/processed page 或 section 数；
- block 数和字符数；
- empty/duplicate/OCR/table issue 数；
- completeness 状态；
- input/config/parser revision；
- 原始与派生 artifact hash。

checkpoint 必须原子写。resume 只重跑失败/未完成 item，不生成不同 block ID，也不重复覆盖成功产物。

## 12.8：安全测试

覆盖：

- 路径遍历和输出目录逃逸；
- HTML/script 内容只作为不可信报告数据；
- PDF decompression bomb/超大页的资源上限；
- 日志不打印整份报告；
- fixture 不含真实公司受限文本；
- external model policy 在 ingestion 阶段只记录，不偷偷上传原文。

## 本章验收

```bash
uv run pytest -q tests/data/disclosures
uv run ruff check src/data/disclosures tests/data/disclosures
uv run mypy src
uv run pytest -q tests/data tests/workflows/test_workflow_contract.py
```

- [ ] TXT/HTML 的每个 block 可回到 source hash 和 offset。
- [ ] 无页码时不制造页码，表格不伪装成普通段落。
- [ ] SEC adapter 不只覆盖 Item 1A，且现有风险 workflow 无回归。
- [ ] A 股采样可复现且不使用绝对路径作为身份。
- [ ] OCR/PDF/table 未支持或失败时产生 issue。
- [ ] ingestion completeness 会进入 workflow state。

本章建议提交：

```text
ch12: add traceable disclosure ingestion adapters
```
