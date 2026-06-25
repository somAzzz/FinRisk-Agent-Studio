"""v17 frontend contract tests.

These tests pin the API payload shapes that the React frontend
consumes. They are intentionally Python-only (no Node) so they
run inside the standard ``uv run pytest`` command. When the
frontend's TypeScript types drift, the matching Python schema
here diverges and a CI run flags it.
"""
