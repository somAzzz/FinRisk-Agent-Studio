"""Repository-wide import smoke test.

The project has several runnable pipelines and agent modules that are not
necessarily imported by the primary API during ordinary unit tests.  This
gate catches stale imports and missing internal modules before those paths
reach a user.
"""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path

import src


def test_all_src_modules_import() -> None:
    failures: list[str] = []
    module_names = sorted(
        module.name
        for module in pkgutil.walk_packages(src.__path__, f"{src.__name__}.")
    )

    for module_name in module_names:
        try:
            importlib.import_module(module_name)
        except Exception as exc:  # pragma: no cover - message is the assertion
            failures.append(f"{module_name}: {type(exc).__name__}: {exc}")

    assert not failures, "module import failures:\n" + "\n".join(failures)


def test_production_source_has_no_removed_agent_runtime() -> None:
    root = Path(__file__).resolve().parents[1]
    removed = [
        root / "src/agents/llm_runtime.py",
        root / "src/agents/runtime.py",
        root / "src/llm/client.py",
        root / "src/llm/deepseek_client.py",
        root / "src/llm/sglang_client.py",
        root / "src/llm/tool_loop.py",
        root / "src/tools/router.py",
    ]
    assert not any(path.exists() for path in removed)

    forbidden = (
        "LLMToolAgentRuntime",
        "src.agents.llm_runtime",
        "src.agents.runtime",
        "src.llm.tool_loop",
        "complete_with_tools",
        "chat_with_tools",
        "EdgarLLMClient",
        "DeepSeekClient",
        "SGLangClient",
        "ToolRouter",
        "src.llm",
        "chat.completions",
        "from openai import",
        "build_graph_interpretation_agent",
        "build_report_generation_agent",
    )
    matches: list[str] = []
    for path in sorted((root / "src").rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        for token in forbidden:
            if token in source:
                matches.append(f"{path.relative_to(root)}: {token}")
    assert not matches, "removed runtime references:\n" + "\n".join(matches)
