"""Repository-wide import smoke test.

The project has several runnable pipelines and agent modules that are not
necessarily imported by the primary API during ordinary unit tests.  This
gate catches stale imports and missing internal modules before those paths
reach a user.
"""

from __future__ import annotations

import importlib
import pkgutil

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
