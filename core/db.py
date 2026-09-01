import sqlite3
from contextlib import closing
from pathlib import Path

from core.constants import TRANSACTION_TYPE_SQL_LIST
from core.secrets import get_secret

PROJECT_ROOT = Path(__file__).resolve().parent.parent
_configured_db_path = get_secret("DATABASE_PATH")
DB_PATH = (
    Path(_configured_db_path).expanduser()
    if _configured_db_path
    else PROJECT_ROOT / "data" / "expenses.db"
)
if not DB_PATH.is_absolute():
    DB_PATH = PROJECT_ROOT / DB_PATH


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def to_cents(amount) -> int:
    return int(round(float(amount) * 100))


def placeholders(count: int) -> str:
    return ",".join("?" * count)


def init_db() -> None:
    with closing(_connect()) as connection:
        _create_tables(connection)
        _create_indexes(connection)
        connection.commit()


def _create_tables(connection: sqlite3.Connection) -> None:
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
