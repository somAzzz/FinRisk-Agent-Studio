"""Transactional schema migrations and SQLite backup helpers for research data."""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

MigrationFunction = Callable[[sqlite3.Connection], None]


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    apply: MigrationFunction

    @property
    def checksum(self) -> str:
        identity = f"{self.version}:{self.name}:{self.apply.__name__}"
        return hashlib.sha256(identity.encode()).hexdigest()


_BASELINE_TABLES = (
    """
    CREATE TABLE IF NOT EXISTS research_theses (
        thesis_id TEXT PRIMARY KEY,
        ticker TEXT NOT NULL,
        status TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        payload TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS research_watchlist (
        ticker TEXT PRIMARY KEY,
        updated_at TEXT NOT NULL,
        payload TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS research_snapshots (
        snapshot_id TEXT PRIMARY KEY,
        ticker TEXT NOT NULL,
        period TEXT NOT NULL,
        as_of TEXT NOT NULL,
        source_fingerprint TEXT NOT NULL,
        created_at TEXT NOT NULL,
        payload TEXT NOT NULL,
        UNIQUE(ticker, period, as_of, source_fingerprint)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_research_snapshots_ticker_as_of
    ON research_snapshots(ticker, as_of DESC)
    """,
    """
    CREATE TABLE IF NOT EXISTS research_runs (
        run_id TEXT PRIMARY KEY,
        ticker TEXT NOT NULL,
        snapshot_id TEXT,
        started_at TEXT NOT NULL,
        state TEXT NOT NULL,
        payload TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS research_changes (
        change_id TEXT PRIMARY KEY,
        ticker TEXT NOT NULL,
        from_snapshot_id TEXT NOT NULL,
        to_snapshot_id TEXT NOT NULL,
        materiality TEXT NOT NULL,
        created_at TEXT NOT NULL,
        payload TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS research_change_reviews (
        change_id TEXT PRIMARY KEY,
        status TEXT NOT NULL,
        notes TEXT,
        reviewed_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS research_expectations (
        expectation_id TEXT PRIMARY KEY,
        ticker TEXT NOT NULL,
        metric TEXT NOT NULL,
        fiscal_period TEXT NOT NULL,
        source TEXT NOT NULL,
        observed_at TEXT NOT NULL,
        as_of TEXT NOT NULL,
        payload TEXT NOT NULL,
        UNIQUE(ticker, metric, fiscal_period, source, observed_at)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS research_alerts (
        alert_id TEXT PRIMARY KEY,
        change_id TEXT NOT NULL UNIQUE,
        ticker TEXT NOT NULL,
        materiality TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL,
        payload TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS research_monitor_cursors (
        ticker TEXT PRIMARY KEY,
        snapshot_id TEXT NOT NULL,
        source_fingerprint TEXT NOT NULL,
        last_success_at TEXT NOT NULL,
        payload TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS post_earnings_review_drafts (
        draft_id TEXT PRIMARY KEY,
        ticker TEXT NOT NULL,
        thesis_id TEXT NOT NULL,
        from_snapshot_id TEXT NOT NULL,
        to_snapshot_id TEXT NOT NULL,
        status TEXT NOT NULL,
        generated_at TEXT NOT NULL,
        payload TEXT NOT NULL,
        UNIQUE(thesis_id, from_snapshot_id, to_snapshot_id)
    )
    """,
)


def _migration_001_initial_research_cycle(connection: sqlite3.Connection) -> None:
    for statement in _BASELINE_TABLES:
        connection.execute(statement)


def _migration_002_peer_groups(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS research_peer_groups (
            peer_group_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            base_ticker TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            payload TEXT NOT NULL
        )
        """
    )


DEFAULT_MIGRATIONS = (
    Migration(1, "initial_research_cycle", _migration_001_initial_research_cycle),
    Migration(2, "peer_groups", _migration_002_peer_groups),
)


def apply_migrations(
    path: Path | str,
    *,
    migrations: Iterable[Migration] = DEFAULT_MIGRATIONS,
    target_version: int | None = None,
) -> int:
    """Apply ordered migrations atomically and return the resulting version."""
    database = Path(path)
    database.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(migrations, key=lambda item: item.version)
    if len({item.version for item in ordered}) != len(ordered):
        raise ValueError("migration versions must be unique")
    maximum = ordered[-1].version if ordered else 0
    target = maximum if target_version is None else target_version
    if target < 0 or target > maximum:
        raise ValueError("target_version is outside the available migration range")

    connection = sqlite3.connect(database)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        if not integrity or integrity[0] != "ok":
            raise RuntimeError("database integrity check failed before migration")
        current = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if current > maximum:
            raise RuntimeError(
                f"database schema version {current} is newer than supported {maximum}"
            )
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS research_schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                checksum TEXT NOT NULL,
                applied_at TEXT NOT NULL
            )
            """
        )
        applied_rows = connection.execute(
            "SELECT version, checksum FROM research_schema_migrations"
        ).fetchall()
        applied = {int(row[0]): str(row[1]) for row in applied_rows}
        for migration in ordered:
            recorded = applied.get(migration.version)
            if recorded is not None and recorded != migration.checksum:
                raise RuntimeError(
                    f"migration checksum mismatch at version {migration.version}"
                )
        for migration in ordered:
            if migration.version <= current or migration.version > target:
                continue
            migration.apply(connection)
            connection.execute(
                """
                INSERT INTO research_schema_migrations
                    (version, name, checksum, applied_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    migration.version,
                    migration.name,
                    migration.checksum,
                    datetime.now(UTC).isoformat(),
                ),
            )
            connection.execute(f"PRAGMA user_version = {migration.version}")
            current = migration.version
        connection.commit()
        return current
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def schema_version(path: Path | str) -> int:
    database = Path(path)
    if not database.exists():
        return 0
    with sqlite3.connect(database) as connection:
        return int(connection.execute("PRAGMA user_version").fetchone()[0])


def verify_integrity(path: Path | str) -> bool:
    with sqlite3.connect(Path(path)) as connection:
        row = connection.execute("PRAGMA integrity_check").fetchone()
    return bool(row and row[0] == "ok")


def backup_database(source: Path | str, destination: Path | str) -> Path:
    source_path = Path(source)
    destination_path = Path(destination)
    if not source_path.exists():
        raise FileNotFoundError(source_path)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    with (
        sqlite3.connect(source_path) as source_connection,
        sqlite3.connect(destination_path) as destination_connection,
    ):
        source_connection.backup(destination_connection)
    if not verify_integrity(destination_path):
        raise RuntimeError("backup integrity check failed")
    return destination_path


def restore_database(backup: Path | str, destination: Path | str) -> Path:
    backup_path = Path(backup)
    destination_path = Path(destination)
    if not verify_integrity(backup_path):
        raise RuntimeError("backup integrity check failed")
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    with (
        sqlite3.connect(backup_path) as backup_connection,
        sqlite3.connect(destination_path) as destination_connection,
    ):
        backup_connection.backup(destination_connection)
    if not verify_integrity(destination_path):
        raise RuntimeError("restored database integrity check failed")
    return destination_path


__all__ = [
    "DEFAULT_MIGRATIONS",
    "Migration",
    "apply_migrations",
    "backup_database",
    "restore_database",
    "schema_version",
    "verify_integrity",
]
