"""Create a standalone SQLite database from the configured PostgreSQL source.

This is a one-time cutover tool. Normal application startup never calls it.
"""

import argparse
import os
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

TABLES = (
    "transactions",
    "diet_meals",
    "diet_foods",
    "diet_ingredients",
    "subscriptions",
    "planned_expenses",
    "batch_submissions",
    "idempotency_keys",
    "budgets",
)


def _read_rows(conn, table: str) -> tuple[tuple[str, ...], list[tuple]]:
    cursor = conn.execute(f"SELECT * FROM {table} ORDER BY 1")
    columns = tuple(
        column.name if hasattr(column, "name") else column[0]
        for column in cursor.description
    )
    return columns, [tuple(row) for row in cursor.fetchall()]


def _target_columns(conn, table: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}


def copy_table(source, target: sqlite3.Connection, table: str) -> int:
    """Copy a table while preserving source column order and explicit ids."""
    source_columns, rows = _read_rows(source, table)
    target_column_names = _target_columns(target, table)
    columns = tuple(
        column for column in source_columns if column in target_column_names
    )
    if not columns:
        raise RuntimeError(f"No compatible columns found for table: {table}")

    source_indexes = [source_columns.index(column) for column in columns]
    values = [tuple(row[index] for index in source_indexes) for row in rows]
    quoted_columns = ", ".join(columns)
    placeholders = ", ".join("?" for _ in columns)
    if values:
        target.executemany(
            f"INSERT INTO {table} ({quoted_columns}) VALUES ({placeholders})", values
        )

    copied_columns, copied_rows = _read_rows(target, table)
    copied_indexes = [copied_columns.index(column) for column in columns]
    copied_values = [
        tuple(row[index] for index in copied_indexes) for row in copied_rows
    ]
    if copied_values != values:
        raise RuntimeError(f"Row verification failed for table: {table}")
    return len(values)


def _initialize_sqlite_target(target: Path) -> str:
    os.environ["DB_BACKEND"] = "sqlite"
    os.environ["DATABASE_PATH"] = str(target)

    # Import after setting the environment because core.db resolves DB_PATH
    # at import time.
    from core.db import get_database_url, init_db

    init_db()
    return get_database_url()


def migrate(target: Path, replace: bool) -> dict[str, int]:
    if target.exists() and not replace:
        raise FileExistsError(
            f"SQLite target already exists: {target}. "
            "Use --replace only after verifying it."
        )

    target.parent.mkdir(parents=True, exist_ok=True)
    temporary_target = target.with_suffix(f"{target.suffix}.tmp")
    if temporary_target.exists():
        raise FileExistsError(
            f"Temporary migration file already exists: {temporary_target}. "
            "Inspect or remove it before retrying."
        )

    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError(
            "Install project dependencies with `uv sync` before migrating."
        ) from exc

    try:
        source_url = _initialize_sqlite_target(temporary_target)
        with (
            closing(psycopg.connect(source_url, prepare_threshold=None)) as source,
            closing(sqlite3.connect(temporary_target)) as destination,
        ):
            destination.row_factory = sqlite3.Row
            destination.execute("PRAGMA foreign_keys = ON")
            counts = {table: copy_table(source, destination, table) for table in TABLES}
            destination.commit()
            integrity = destination.execute("PRAGMA integrity_check").fetchone()[0]
            foreign_key_violations = destination.execute(
                "PRAGMA foreign_key_check"
            ).fetchall()
            if integrity != "ok" or foreign_key_violations:
                raise RuntimeError(
                    "SQLite integrity validation failed: "
                    f"integrity_check={integrity}, "
                    f"foreign_key_violations={foreign_key_violations}"
                )
        os.replace(temporary_target, target)
    except Exception:
        if temporary_target.exists():
            temporary_target.unlink()
        raise

    return counts


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Copy the configured PostgreSQL database into a verified SQLite file."
        )
    )
    parser.add_argument(
        "--target",
        type=Path,
        required=True,
        help="New SQLite file path, for example data/expenses.db.",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Replace an existing target only after a successful conversion.",
    )
    args = parser.parse_args()

    counts = migrate(args.target.resolve(), args.replace)
    print(f"SQLite migration complete: {args.target.resolve()}")
    for table, count in counts.items():
        print(f"{table}: {count}")


if __name__ == "__main__":
    main()
