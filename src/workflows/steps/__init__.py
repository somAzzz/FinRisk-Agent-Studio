"""Step implementations for the FinRisk Agent Studio workflow.

Each step is a small class that:
- exposes ``name`` for trace identification,
- implements ``async def run(self, state) -> state``,
- handles its own trace event,
- never raises on best-effort steps (records error in trace instead).

Heavy lifting is delegated to existing modules:
``src.data.*`` for SEC / transcript ingestion,
``src.tools.*`` for search,
``src.graph.*`` for graph reasoning,
``src.schemas.finrisk.*`` for typed I/O.
"""