import hashlib
import json
import sqlite3
from collections.abc import Callable
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from backend.constants import TRANSACTION_TYPE_SQL_LIST, TYPE_EXPENSE
from backend.paths import database_path


def connect(path: Path | None = None, *, readonly: bool = False) -> sqlite3.Connection:
    """Open either instance database with consistent SQLite connection settings."""
    path = path if path is not None else database_path()
    if readonly:
        connection = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True, timeout=5)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path, timeout=5)
        connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA busy_timeout = 5000")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def to_cents(amount) -> int:
    return int(round(float(amount) * 100))


def placeholders(count: int) -> str:
    return ",".join("?" * count)


def init_db() -> None:
    with closing(connect()) as connection:
        create_tables(connection)
        create_indexes(connection)
        connection.commit()


def create_tables(connection: sqlite3.Connection) -> None:
    connection.execute("""
        CREATE TABLE IF NOT EXISTS capture_submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            original_text TEXT NOT NULL,
            default_date TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        )
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS capture_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            submission_id INTEGER NOT NULL REFERENCES capture_submissions(id),
            parent_id INTEGER REFERENCES capture_items(id),
            source_text TEXT NOT NULL,
            default_date TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN
                ('queued', 'processing', 'review', 'failed', 'expanded', 'saved', 'discarded')),
            record_json TEXT,
            reason TEXT NOT NULL DEFAULT '',
            claim_token TEXT,
            result_id INTEGER,
            result_type TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        )
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS capture_phrases (
            text TEXT PRIMARY KEY,
            created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        )
    """)
    connection.execute(f"""
        CREATE TABLE IF NOT EXISTS transactions (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            type                TEXT NOT NULL
                                CHECK(type IN ({TRANSACTION_TYPE_SQL_LIST})),
            description         TEXT NOT NULL,
            amount              REAL NOT NULL,
            amount_cents        INTEGER,
            date                TEXT NOT NULL,
            category            TEXT,
            subcategory         TEXT,
            notes               TEXT,
            confidence          REAL,
            refund_for_id       INTEGER,
            coverage_start      TEXT,
            coverage_end        TEXT,
            reviewed            INTEGER DEFAULT 0,
            subscription_id     INTEGER,
            created_at          TEXT DEFAULT (datetime('now', 'localtime')),
            CHECK ((coverage_start IS NULL AND coverage_end IS NULL) OR
                (type = '{TYPE_EXPENSE}' AND coverage_start IS NOT NULL AND coverage_end IS NOT NULL
                 AND coverage_start GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'
                 AND coverage_end GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'
                 AND coverage_start >= '0001-01-01'
                 AND date(coverage_start, '+0 days') IS coverage_start
                 AND date(coverage_end, '+0 days') IS coverage_end
                 AND coverage_start <= coverage_end))
        )
    """)
    connection.execute("""
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
    connection.execute("""
        CREATE TABLE IF NOT EXISTS diet_foods (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            meal_id   INTEGER NOT NULL REFERENCES diet_meals(id) ON DELETE CASCADE,
            food_name TEXT NOT NULL,
            quantity  TEXT
        )
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS diet_ingredients (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            food_id         INTEGER NOT NULL REFERENCES diet_foods(id)
                            ON DELETE CASCADE,
            ingredient_name TEXT NOT NULL
        )
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            name                    TEXT NOT NULL,
            vendor                  TEXT,
            amount                  REAL NOT NULL,
            amount_cents            INTEGER,
            start_date              TEXT,
            next_renewal_date       TEXT,
            end_date                TEXT,
            category                TEXT,
            subcategory             TEXT,
            payment_method          TEXT,
            auto_renew              INTEGER DEFAULT 1,
            status                  TEXT DEFAULT 'active',
            notes                   TEXT,
            renewal_mode            TEXT DEFAULT 'same_day',
            renewal_interval        INTEGER,
            renewal_anchor_day      INTEGER,
            last_payment_date       TEXT,
            coverage_unit           TEXT,
            coverage_interval       INTEGER,
            created_at              TEXT DEFAULT (datetime('now', 'localtime')),
            CHECK ((coverage_unit IS NULL AND coverage_interval IS NULL) OR
                (coverage_unit IS NOT NULL AND coverage_unit IN ('months', 'days')
                 AND typeof(coverage_interval) = 'integer' AND coverage_interval > 0))
        )
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS planned_expenses (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            description     TEXT NOT NULL,
            amount          REAL NOT NULL,
            amount_cents    INTEGER,
            due_date        TEXT,
            category        TEXT,
            subcategory     TEXT,
            notes           TEXT,
            subscription_id INTEGER,
            transaction_id  INTEGER,
            status          TEXT NOT NULL DEFAULT 'open',
            created_at      TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS batch_submissions (
            submission_id TEXT PRIMARY KEY,
            payload_hash  TEXT NOT NULL,
            record_count  INTEGER NOT NULL,
            created_at    TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS idempotency_keys (
            idempotency_key TEXT PRIMARY KEY,
            operation       TEXT NOT NULL,
            payload_hash    TEXT NOT NULL,
            response_json   TEXT,
            created_at      TEXT NOT NULL
        )
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS budgets (
            month                  TEXT PRIMARY KEY,
            amortized_budget_cents INTEGER,
            cash_budget_cents      INTEGER
        )
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS notes (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            title         TEXT NOT NULL DEFAULT '',
            content       TEXT NOT NULL CHECK(length(trim(content)) > 0),
            recorded_date TEXT NOT NULL,
            created_at    TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
            updated_at    TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        )
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS note_event_dates (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            note_id    INTEGER NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
            start_date TEXT NOT NULL,
            end_date   TEXT NOT NULL,
            CHECK(start_date <= end_date)
        )
    """)


def create_indexes(connection: sqlite3.Connection) -> None:
    for statement in (
        "CREATE INDEX IF NOT EXISTS idx_capture_items_status ON capture_items(status, id)",
        "CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(date)",
        """CREATE INDEX IF NOT EXISTS idx_transactions_filter
           ON transactions(type, category, subcategory, date)""",
        """CREATE INDEX IF NOT EXISTS idx_transactions_refund_for
           ON transactions(refund_for_id)""",
        """CREATE INDEX IF NOT EXISTS idx_transactions_subscription
           ON transactions(subscription_id)""",
        """CREATE INDEX IF NOT EXISTS idx_planned_expenses_transaction
           ON planned_expenses(transaction_id)""",
        "CREATE INDEX IF NOT EXISTS idx_notes_recorded_date ON notes(recorded_date DESC, id DESC)",
        """CREATE INDEX IF NOT EXISTS idx_note_event_dates_note
           ON note_event_dates(note_id, start_date, end_date)""",
    ):
        connection.execute(statement)


class IdempotencyConflict(ValueError):
    pass


def execute_idempotent(
    operation: str,
    idempotency_key: str,
    payload: dict,
    action: Callable[[sqlite3.Connection], dict],
) -> tuple[dict, bool]:
    key = str(idempotency_key or "").strip()
    if not key:
        raise ValueError("写入请求缺少 Idempotency-Key")
    payload_hash = hash_payload(payload)

    with closing(connect()) as conn:
        try:
            inserted = conn.execute(
                """INSERT INTO idempotency_keys
                   (idempotency_key, operation, payload_hash, response_json, created_at)
                   VALUES (?, ?, ?, NULL, ?)
                   ON CONFLICT(idempotency_key) DO NOTHING""",
                (
                    key,
                    operation,
                    payload_hash,
                    datetime.now(UTC).isoformat(),
                ),
            )
            if inserted.rowcount == 0:
                existing = conn.execute(
                    """SELECT operation, payload_hash, response_json
                       FROM idempotency_keys WHERE idempotency_key = ?""",
                    (key,),
                ).fetchone()
                if (
                    existing is None
                    or existing["operation"] != operation
                    or existing["payload_hash"] != payload_hash
                    or not existing["response_json"]
                ):
                    raise IdempotencyConflict("同一幂等键已用于不同的写入请求")
                return json.loads(existing["response_json"]), True

            response = action(conn)
            conn.execute(
                """UPDATE idempotency_keys SET response_json = ?
                   WHERE idempotency_key = ?""",
                (
                    json.dumps(response, ensure_ascii=False, default=str),
                    key,
                ),
            )
            conn.commit()
            return response, False
        except Exception:
            conn.rollback()
            raise


def hash_payload(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()
