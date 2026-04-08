import sqlite3
from contextlib import closing
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "expenses.db"


def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with closing(_connect()) as conn:
        # Clean break: remove old single-table diet schema if present
        conn.execute("DROP TABLE IF EXISTS diet_entries")

        conn.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            type        TEXT NOT NULL CHECK(type IN ('收入', '支出', '迁移')),
            description TEXT NOT NULL,
            amount      REAL NOT NULL,
            date        TEXT NOT NULL,
            category    TEXT,
            subcategory TEXT,
            notes       TEXT,
            confidence  REAL,
            created_at  TEXT DEFAULT (datetime('now', 'localtime'))
        )
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS diet_meals (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            date        TEXT NOT NULL,
            time        TEXT,
            meal_type   TEXT,
            description TEXT NOT NULL,
            notes       TEXT,
            confidence  REAL,
            created_at  TEXT DEFAULT (datetime('now', 'localtime'))
        )
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS diet_foods (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            meal_id     INTEGER NOT NULL REFERENCES diet_meals(id) ON DELETE CASCADE,
            food_name   TEXT NOT NULL,
            quantity    TEXT
        )
        """)

        conn.commit()
