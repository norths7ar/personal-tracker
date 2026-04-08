import sqlite3
from contextlib import closing
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "expenses.db"


def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with closing(_connect()) as conn:
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
        CREATE TABLE IF NOT EXISTS diet_entries (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            date        TEXT NOT NULL,
            time        TEXT,
            description TEXT NOT NULL,
            meal_type   TEXT,
            food_name   TEXT,
            quantity    TEXT,
            notes       TEXT,
            confidence  REAL,
            created_at  TEXT DEFAULT (datetime('now', 'localtime'))
        )
        """)
        conn.commit()
