# Step 02 - Hugging Face EDGAR Streaming Loader

## 目标

把当前本地 JSONL 读取方式升级为 Hugging Face streaming-first 的 EDGAR 数据加载方式，同时保留本地 loader 作为 fallback。

当前代码：

```text
src/data/loader.py
```

目前它默认读取本地 `data/edgar_2020/*.jsonl`。本步骤要新增 Hugging Face loader，而不是直接删除旧逻辑。

## 需要新增或修改的文件

新增：

```text
src/data/edgar_hf.py
src/data/filing_utils.py
tests/data/test_edgar_hf.py
```

修改：

```text
src/data/__init__.py
src/data/loader.py
pyproject.toml
```

## 设计目标

新增 `EdgarCorpusLoader`：

```python
class EdgarCorpusLoader:
    def __init__(
        self,
        dataset_name: str = "eloukas/edgar-corpus",
        config_name: str = "year_2020",
        split: str = "train",
        streaming: bool = True,
    ):
        ...

    def iter_filings(
        self,
        min_section_length: int = 100,
        required_sections: Sequence[str] = ("section_1A",),
        limit: int | None = None,
    ) -> Iterator[FilingRecord]:
        ...
```

## 数据映射

Hugging Face 原始字段映射到 `FilingRecord`：

| HF 字段 | FilingRecord 字段 |
| --- | --- |
| `cik` | `cik` |
| `year` | `year` |
| `filename` | `metadata["filename"]` |
| `section_1` | `sections["section_1"]` |
| `section_1A` | `sections["section_1A"]` |
| `section_7` | `sections["section_7"]` |
| 其它 section | `sections[...]` |

`source` 固定为 `"huggingface"`。

`source_id` 建议格式：

```text
hf:eloukas/edgar-corpus:year_2020:train:<row_index>
```

## 实施任务

1. 在 `src/data/edgar_hf.py` 中实现 Hugging Face loader。
2. 使用 `datasets.load_dataset(dataset_name, config_name, split=split, streaming=streaming)`。
3. 实现 section 过滤：
   - required section 存在
   - section 长度大于阈值
4. 实现 `limit` 参数，方便测试和 demo。
5. 处理 `year` 可能是字符串的问题，统一转 int。
6. 将所有 section 字段收集到 `FilingRecord.sections`。
7. 在 `src/data/__init__.py` 中导出 `EdgarCorpusLoader`。
8. 保留 `EdgarDataset`，但在 docstring 中标记为 local JSONL loader。

## 测试策略

不要让默认单元测试依赖真实 Hugging Face 网络。

测试方法：

- mock `datasets.load_dataset`
- 返回 list 或 generator
- 验证：
  - streaming 参数传递正确
  - section 映射正确
  - required section 过滤正确
  - limit 生效
  - year 转换正确

示例测试：

```python
def test_iter_filings_maps_hf_record_to_filing_record(monkeypatch):
    ...
```

可选增加集成测试：

```bash
RUN_HF_INTEGRATION=1 pytest tests/data/test_edgar_hf.py -m integration
```

## 验收标准

- 可以运行：

```python
from src.data import EdgarCorpusLoader

loader = EdgarCorpusLoader(config_name="year_2020", split="train", streaming=True)
first = next(loader.iter_filings(limit=1))
```

- 单元测试不访问真实网络。
- 旧的 `EdgarDataset` 仍可使用。
- 不破坏 `tests/llm`、`tests/tools`、`tests/browser`。

## 后续步骤依赖

Step 07 的 filing extraction pipeline 会使用本 loader。

