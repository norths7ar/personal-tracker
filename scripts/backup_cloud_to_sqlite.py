"""Create a rolling local SQLite backup from the hosted PostgreSQL database."""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from contextlib import closing
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core import db as core_db

BACKUP_TABLES = (
    "transactions",
    "diet_meals",
    "diet_foods",
    "subscriptions",
    "budgets",
)
DEFAULT_BACKUP_DIR = PROJECT_ROOT / "data" / "backups" / "cloud"
DEFAULT_LOCAL_BACKUP_DIR = PROJECT_ROOT / "data" / "backups" / "local"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Back up the hosted PostgreSQL data as a local SQLite snapshot."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_BACKUP_DIR,
        help=f"Snapshot directory (default: {DEFAULT_BACKUP_DIR})",
    )
    parser.add_argument(
        "--keep", type=int, default=10, help="Number of recent snapshots to retain."
    )
    parser.add_argument(
        "--refresh-local",
        action="store_true",
        help="Replace data/expenses.db after a successful cloud snapshot.",
    )
    return parser.parse_args()


def initialize_snapshot(path: Path) -> sqlite3.Connection:
    """Create the current application schema without connecting to the configured DB."""
    raw_connection = sqlite3.connect(path)
    raw_connection.row_factory = sqlite3.Row
    raw_connection.execute("PRAGMA foreign_keys = ON")
    connection = core_db.Connection(raw_connection, "sqlite")
    core_db._init_sqlite(connection)
    core_db._ensure_transaction_amount_cents(connection)
    core_db._ensure_transaction_workflow_columns(connection)
    core_db._ensure_subscription_amount_cents(connection)
    core_db._ensure_subscription_payment_type(connection)
    core_db._init_budgets(connection)
    raw_connection.commit()
    return raw_connection


def sqlite_columns(connection: sqlite3.Connection, table_name: str) -> list[str]:
    return [
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    ]


def postgres_columns(connection, table_name: str) -> list[str]:
    rows = connection.execute(
        """SELECT column_name
           FROM information_schema.columns
           WHERE table_schema = 'public' AND table_name = %s
           ORDER BY ordinal_position""",
        (table_name,),
    ).fetchall()
    return [row["column_name"] for row in rows]


def copy_table(remote_connection, local_connection: sqlite3.Connection, table_name: str) -> int:
    local_columns = sqlite_columns(local_connection, table_name)
    remote_columns = postgres_columns(remote_connection, table_name)
    if not remote_columns:
        return 0
    missing_columns = set(local_columns) - set(remote_columns)
    if missing_columns:
        raise RuntimeError(
            f"Cloud table {table_name} is missing local columns: {', '.join(sorted(missing_columns))}"
        )

    column_sql = ", ".join(local_columns)
    order_column = "id" if "id" in local_columns else "month"
    rows = remote_connection.execute(
        f"SELECT {column_sql} FROM public.{table_name} ORDER BY {order_column}"
    ).fetchall()
    placeholders = ", ".join("?" for _ in local_columns)
    local_connection.executemany(
        f"INSERT INTO {table_name} ({column_sql}) VALUES ({placeholders})",
        [[row[column] for column in local_columns] for row in rows],
    )
    return len(rows)


def verify_snapshot(path: Path, expected_counts: dict[str, int]) -> None:
    with closing(sqlite3.connect(path)) as connection:
        counts = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in BACKUP_TABLES
        }
        foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()

    if counts != expected_counts:
        raise RuntimeError(f"Snapshot row-count mismatch: expected {expected_counts}, got {counts}")
    if foreign_key_errors:
        raise RuntimeError("Snapshot foreign-key validation failed")


def prune_backups(output_dir: Path, keep: int) -> None:
    snapshots = sorted(
        output_dir.glob("cloud-*.db"), key=lambda path: path.name, reverse=True
    )
    for snapshot in snapshots[keep:]:
        snapshot.unlink()


def refresh_local_database(snapshot: Path) -> Path:
    """Archive the previous local DB, then atomically replace it with the snapshot."""
    local_database = core_db.DB_PATH
    if local_database.exists():
        DEFAULT_LOCAL_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        local_archive = DEFAULT_LOCAL_BACKUP_DIR / f"before-cloud-refresh-{timestamp}.db"
        shutil.copy2(local_database, local_archive)

    local_database.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = local_database.with_suffix(".db.tmp")
    shutil.copy2(snapshot, temporary_path)
    temporary_path.replace(local_database)
    return local_database


def create_backup(output_dir: Path, keep: int, refresh_local: bool) -> tuple[Path, dict[str, int]]:
    if keep < 1:
        raise ValueError("--keep must be at least 1")

    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    snapshot_path = output_dir / f"cloud-{timestamp}.db"
    temporary_path = output_dir / f".cloud-{timestamp}.tmp"

    try:
        with closing(core_db._connect_postgres()) as remote_connection:
            with closing(initialize_snapshot(temporary_path)) as local_connection:
                expected_counts = {
                    table: copy_table(remote_connection, local_connection, table)
                    for table in BACKUP_TABLES
                }
                local_connection.commit()

        verify_snapshot(temporary_path, expected_counts)
        temporary_path.replace(snapshot_path)
        prune_backups(output_dir, keep)
        if refresh_local:
            refresh_local_database(snapshot_path)
        return snapshot_path, expected_counts
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def main() -> None:
    args = parse_args()
    snapshot, counts = create_backup(args.output_dir, args.keep, args.refresh_local)
    print(f"Created cloud backup: {snapshot}")
    print(
        "Rows: " + ", ".join(f"{table}={count}" for table, count in counts.items())
    )
    if args.refresh_local:
        print(f"Refreshed local database: {core_db.DB_PATH}")


if __name__ == "__main__":
    main()
