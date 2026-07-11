from __future__ import annotations

import sqlite3

import pytest

from src.research.database import (
    DEFAULT_MIGRATIONS,
    Migration,
    apply_migrations,
    backup_database,
    restore_database,
    schema_version,
    verify_integrity,
)
from src.research.journal import InvestmentThesis, ResearchJournalStore, WatchlistItem


def test_legacy_database_upgrades_without_losing_journal_data(tmp_path) -> None:
    path = tmp_path / "legacy.sqlite"
    thesis = InvestmentThesis(
        thesis_id="legacy-thesis",
        ticker="ACME",
        statement="Legacy thesis remains intact",
        time_horizon="12 months",
        disconfirming_conditions=["Revenue declines"],
    )
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE research_theses (
                thesis_id TEXT PRIMARY KEY,
                ticker TEXT NOT NULL,
                status TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                payload TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "INSERT INTO research_theses VALUES (?, ?, ?, ?, ?)",
            (
                thesis.thesis_id,
                thesis.ticker,
                thesis.status,
                thesis.updated_at.isoformat(),
                thesis.model_dump_json(),
            ),
        )

    assert apply_migrations(path) == 2
    assert apply_migrations(path) == 2
    assert schema_version(path) == 2
    assert ResearchJournalStore(path).get_thesis(thesis.thesis_id) == thesis
    with sqlite3.connect(path) as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM research_schema_migrations"
        ).fetchone()[0]
    assert count == 2


def test_failed_migration_rolls_back_schema_and_version(tmp_path) -> None:
    path = tmp_path / "failure.sqlite"
    apply_migrations(path)

    def fail_after_ddl(connection: sqlite3.Connection) -> None:
        connection.execute("CREATE TABLE must_rollback (value TEXT)")
        raise RuntimeError("forced migration failure")

    migrations = (
        *DEFAULT_MIGRATIONS,
        Migration(3, "forced_failure", fail_after_ddl),
    )
    with pytest.raises(RuntimeError, match="forced migration failure"):
        apply_migrations(path, migrations=migrations)

    assert schema_version(path) == 2
    with sqlite3.connect(path) as connection:
        row = connection.execute(
            "SELECT name FROM sqlite_master WHERE name = 'must_rollback'"
        ).fetchone()
    assert row is None


def test_online_backup_and_restore_preserve_consistent_snapshot(tmp_path) -> None:
    source = tmp_path / "research.sqlite"
    backup = tmp_path / "backups" / "research.sqlite"
    journal = ResearchJournalStore(source)
    journal.save_watchlist_item(WatchlistItem(ticker="AAPL"))

    backup_database(source, backup)
    journal.save_watchlist_item(WatchlistItem(ticker="NVDA"))
    assert {item.ticker for item in journal.list_watchlist()} == {"AAPL", "NVDA"}

    restore_database(backup, source)
    restored = ResearchJournalStore(source)
    assert [item.ticker for item in restored.list_watchlist()] == ["AAPL"]
    assert verify_integrity(source)
