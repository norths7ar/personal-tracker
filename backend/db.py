import hashlib
import json
import sqlite3
from collections.abc import Callable
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from backend.constants import TRANSACTION_TYPE_SQL_LIST
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
        _create_tables(connection)
        _create_indexes(connection)
        connection.commit()


def _create_tables(connection: sqlite3.Connection) -> None:
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
    connection.execute("""
        CREATE TABLE IF NOT EXISTS todos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL CHECK(length(trim(title)) > 0),
            notes TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK(status IN ('pending', 'active', 'completed')),
            position INTEGER NOT NULL,
            completed_at TEXT,
            CHECK((status = 'completed') = (completed_at IS NOT NULL))
        )
    """)
    connection.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_todos_one_active
        ON todos(status) WHERE status = 'active'
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
            amortization_months INTEGER,
            amortization_start  TEXT,
            reviewed            INTEGER DEFAULT 0,
            subscription_id     INTEGER,
            created_at          TEXT DEFAULT (datetime('now', 'localtime'))
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
            billing_cycle           TEXT NOT NULL,
            billing_interval_months INTEGER,
            start_date              TEXT,
            next_renewal_date       TEXT,
            end_date                TEXT,
            category                TEXT,
            subcategory             TEXT,
            payment_method          TEXT,
            auto_renew              INTEGER DEFAULT 1,
            status                  TEXT DEFAULT 'active',
            notes                   TEXT,
            payment_type            TEXT DEFAULT 'subscription',
            transaction_id          INTEGER,
            renewal_mode            TEXT DEFAULT 'same_day',
            renewal_interval        INTEGER,
            renewal_anchor_day      INTEGER,
            last_payment_date       TEXT,
            created_at              TEXT DEFAULT (datetime('now', 'localtime'))
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


def _create_indexes(connection: sqlite3.Connection) -> None:
    for statement in (
        "CREATE INDEX IF NOT EXISTS idx_capture_items_status ON capture_items(status, id)",
        "CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(date)",
        """CREATE INDEX IF NOT EXISTS idx_transactions_filter
           ON transactions(type, category, subcategory, date)""",
        """CREATE INDEX IF NOT EXISTS idx_transactions_refund_for
           ON transactions(refund_for_id)""",
        """CREATE INDEX IF NOT EXISTS idx_transactions_subscription
           ON transactions(subscription_id)""",
        """CREATE INDEX IF NOT EXISTS idx_subscriptions_transaction
           ON subscriptions(transaction_id)""",
        """CREATE INDEX IF NOT EXISTS idx_planned_expenses_transaction
           ON planned_expenses(transaction_id)""",
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
