import argparse
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.db import DB_PATH, _connect, get_backend, init_db


TABLES = ("transactions", "diet_meals", "diet_foods")


def _sqlite_rows(db_path: Path, table: str) -> list[dict]:
    with closing(sqlite3.connect(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY id").fetchall()]


def _target_counts(conn) -> dict[str, int]:
    return {
        table: conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"]
        for table in TABLES
    }


def _insert_transactions(conn, rows: list[dict]):
    if not rows:
        return
    conn.executemany(
        """INSERT INTO transactions
           (id, type, description, amount, amount_cents, date, category, subcategory,
            notes, confidence, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            (
                row["id"],
                row["type"],
                row["description"],
                row["amount"],
                row.get("amount_cents"),
                row["date"],
                row.get("category"),
                row.get("subcategory"),
                row.get("notes"),
                row.get("confidence"),
                row.get("created_at"),
            )
            for row in rows
        ],
    )


def _insert_meals(conn, rows: list[dict]):
    if not rows:
        return
    conn.executemany(
        """INSERT INTO diet_meals
           (id, date, time, meal_type, description, notes, confidence, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            (
                row["id"],
                row["date"],
                row.get("time"),
                row.get("meal_type"),
                row["description"],
                row.get("notes"),
                row.get("confidence"),
                row.get("created_at"),
            )
            for row in rows
        ],
    )


def _insert_foods(conn, rows: list[dict]):
    if not rows:
        return
    conn.executemany(
        """INSERT INTO diet_foods
           (id, meal_id, food_name, quantity)
           VALUES (?, ?, ?, ?)""",
        [
            (
                row["id"],
                row["meal_id"],
                row["food_name"],
                row.get("quantity"),
            )
            for row in rows
        ],
    )


def _reset_sequences(conn):
    for table in TABLES:
        conn.execute(
            f"""SELECT setval(
                    pg_get_serial_sequence('{table}', 'id'),
                    COALESCE((SELECT MAX(id) FROM {table}), 1),
                    true
                )"""
        )


def migrate(source: Path, allow_nonempty: bool):
    if get_backend() not in {"postgres", "postgresql"}:
        raise RuntimeError("Set DB_BACKEND=postgres before running this migration.")
    if not source.exists():
        raise FileNotFoundError(f"SQLite database not found: {source}")

    init_db()
    source_rows = {table: _sqlite_rows(source, table) for table in TABLES}

    with closing(_connect()) as conn:
        counts_before = _target_counts(conn)
        if any(counts_before.values()) and not allow_nonempty:
            raise RuntimeError(
                "Target PostgreSQL database is not empty. Re-run with --allow-nonempty "
                "only if you have checked that duplicate ids will not conflict."
            )

        _insert_transactions(conn, source_rows["transactions"])
        _insert_meals(conn, source_rows["diet_meals"])
        _insert_foods(conn, source_rows["diet_foods"])
        _reset_sequences(conn)
        conn.commit()
        counts_after = _target_counts(conn)

    print("Migration complete.")
    for table in TABLES:
        print(
            f"{table}: source={len(source_rows[table])}, "
            f"target_before={counts_before[table]}, target_after={counts_after[table]}"
        )


def main():
    parser = argparse.ArgumentParser(description="Migrate local SQLite data to PostgreSQL.")
    parser.add_argument(
        "--source",
        type=Path,
        default=DB_PATH,
        help=f"SQLite database path. Default: {DB_PATH}",
    )
    parser.add_argument(
        "--allow-nonempty",
        action="store_true",
        help="Allow importing into a non-empty PostgreSQL database.",
    )
    args = parser.parse_args()
    migrate(args.source, args.allow_nonempty)


if __name__ == "__main__":
    main()
