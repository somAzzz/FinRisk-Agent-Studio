"""Thin wrapper around the official neo4j Python driver.

The driver import is guarded so unit tests can run on machines where
``neo4j`` is not installed. The class exposes a ``_execute`` seam that
tests can monkeypatch in place of the real driver session.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src.config import get_settings

if TYPE_CHECKING:
    pass


def _load_neo4j() -> Any:
    """Import the official neo4j driver or raise a helpful error."""
    try:
        import neo4j  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - exercised only w/o driver
        msg = (
            "The 'neo4j' package is required to use Neo4jClient. "
            "Install it with `uv add neo4j` or `pip install neo4j>=5.0.0`."
        )
        raise ImportError(msg) from exc
    return neo4j


class Neo4jClient:
    """Minimal context-managed wrapper around a ``neo4j.Driver``."""

    def __init__(
        self,
        uri: str | None = None,
        user: str | None = None,
        password: str | None = None,
    ) -> None:
        settings = get_settings()
        self._uri = uri or settings.neo4j_uri
        self._user = user or settings.neo4j_user
        self._password = password if password is not None else settings.neo4j_password
        if self._password is None:
            msg = "Neo4j password is required (set NEO4J_PASSWORD)."
            raise ValueError(msg)

        neo4j = _load_neo4j()
        # ``with_dependencies_check`` is unavailable in older driver
        # versions; fall back to the bare ``GraphDatabase.driver``.
        driver_factory = getattr(neo4j, "GraphDatabase", None)
        if driver_factory is None:
            msg = "neo4j driver is missing GraphDatabase; please reinstall neo4j."
            raise ImportError(msg)
        self._driver = driver_factory.driver(
            self._uri, auth=(self._user, self._password)
        )

    # -- test seam ---------------------------------------------------------
    def _execute(self, cypher: str, parameters: dict[str, Any] | None) -> list[dict]:
        """Run a single query and return records as plain dicts.

        Tests monkeypatch this method. The default implementation
        delegates to the underlying driver session.
        """
        params = parameters or {}
        records: list[dict] = []
        with self._driver.session() as session:
            result = session.run(cypher, **params)
            for record in result:
                records.append(dict(record))
        return records

    # -- public API --------------------------------------------------------
    def run(self, cypher: str, parameters: dict[str, Any] | None = None) -> list[dict]:
        """Execute ``cypher`` with ``parameters`` and return record dicts."""
        return list(self._execute(cypher, parameters))

    def close(self) -> None:
        """Close the underlying driver (idempotent)."""
        close = getattr(self._driver, "close", None)
        if callable(close):
            close()

    # -- context manager ---------------------------------------------------
    def __enter__(self) -> Neo4jClient:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
