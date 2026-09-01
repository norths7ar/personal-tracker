import sqlite3
from contextlib import closing
from pathlib import Path

from core.constants import SUBSCRIPTION_CYCLE_ONE_TIME, TRANSACTION_TYPE_SQL_LIST
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


def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def to_cents(amount) -> int:
    return int(round(float(amount) * 100))


def placeholders(count: int) -> str:
    return ",".join("?" * count)


def init_db():
    with closing(_connect()) as conn:
        _init_sqlite(conn)

        _ensure_transaction_amount_cents(conn)
        _ensure_transaction_workflow_columns(conn)
        _ensure_subscription_amount_cents(conn)
        _ensure_subscription_payment_type(conn)
        _ensure_subscription_renewal_columns(conn)
        _ensure_planned_expense_columns(conn)
        _ensure_batch_submission_schema(conn)
        _ensure_idempotency_schema(conn)
        _ensure_query_indexes(conn)
        _init_budgets(conn)
        _migrate_amortized_to_subscriptions(conn)
        conn.commit()


def _init_sqlite(conn):
    conn.execute(f"""
    CREATE TABLE IF NOT EXISTS transactions (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        type        TEXT NOT NULL CHECK(type IN ({TRANSACTION_TYPE_SQL_LIST})),
        description TEXT NOT NULL,
        amount      REAL NOT NULL,
        amount_cents INTEGER,
        date        TEXT NOT NULL,
        category    TEXT,
        subcategory TEXT,
        notes       TEXT,
        confidence  REAL,
        reviewed    INTEGER DEFAULT 0,
        subscription_id INTEGER,
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

    conn.execute("""
    CREATE TABLE IF NOT EXISTS diet_ingredients (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        food_id         INTEGER NOT NULL REFERENCES diet_foods(id) ON DELETE CASCADE,
        ingredient_name TEXT NOT NULL
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS subscriptions (
        id                 INTEGER PRIMARY KEY AUTOINCREMENT,
        name               TEXT NOT NULL,
        vendor             TEXT,
        amount             REAL NOT NULL,
        amount_cents       INTEGER,
        billing_cycle      TEXT NOT NULL,
        billing_interval_months INTEGER,
        start_date         TEXT,
        next_renewal_date  TEXT,
        end_date           TEXT,
        category           TEXT,
        subcategory        TEXT,
        payment_method     TEXT,
        auto_renew         INTEGER DEFAULT 1,
        status             TEXT DEFAULT 'active',
        notes              TEXT,
        renewal_mode       TEXT,
        renewal_interval   INTEGER,
        renewal_anchor_day INTEGER,
        last_payment_date  TEXT,
        created_at         TEXT DEFAULT (datetime('now', 'localtime'))
    )
    """)


def _create_budgets_table(conn):
    """Store monthly targets separately from immutable transaction facts."""
    conn.execute(
        """CREATE TABLE IF NOT EXISTS budgets (
            month                   TEXT PRIMARY KEY,
            amortized_budget_cents  INTEGER,
            cash_budget_cents       INTEGER
        )"""
    )


def _ensure_transaction_amount_cents(conn):
    columns = _transaction_columns(conn)
    if "amount_cents" not in columns:
        conn.execute("ALTER TABLE transactions ADD COLUMN amount_cents INTEGER")
    conn.execute(
        """UPDATE transactions
           SET amount_cents = CAST(ROUND(amount * 100) AS INTEGER)
           WHERE amount_cents IS NULL AND amount IS NOT NULL"""
    )


def _transaction_columns(conn) -> set[str]:
    return {
        row["name"]
        for row in conn.execute("PRAGMA table_info(transactions)").fetchall()
    }


def _table_columns(conn, table_name: str) -> set[str]:
    return {
        row["name"]
        for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    }


def _ensure_transaction_workflow_columns(conn):
    columns = _transaction_columns(conn)
    additions = {
        "refund_for_id": "INTEGER",
        "amortization_months": "INTEGER",
        "amortization_start": "TEXT",
        "subscription_id": "INTEGER",
        "reviewed": "INTEGER DEFAULT 0",
    }
    for name, definition in additions.items():
        if name not in columns:
            conn.execute(f"ALTER TABLE transactions ADD COLUMN {name} {definition}")


def _ensure_subscription_payment_type(conn):
    columns = _table_columns(conn, "subscriptions")
    if "payment_type" not in columns:
        conn.execute(
            """ALTER TABLE subscriptions
               ADD COLUMN payment_type TEXT DEFAULT 'subscription'"""
        )
        conn.execute(
            """UPDATE subscriptions
               SET payment_type = 'subscription'
               WHERE payment_type IS NULL"""
        )
    if "transaction_id" not in columns:
        conn.execute("ALTER TABLE subscriptions ADD COLUMN transaction_id INTEGER")


def _ensure_subscription_renewal_columns(conn):
    columns = _table_columns(conn, "subscriptions")
    additions = {
        "renewal_mode": "TEXT DEFAULT 'same_day'",
        "renewal_interval": "INTEGER",
        "renewal_anchor_day": "INTEGER",
        "last_payment_date": "TEXT",
    }
    for name, definition in additions.items():
        if name not in columns:
            conn.execute(f"ALTER TABLE subscriptions ADD COLUMN {name} {definition}")

    conn.execute(
        """UPDATE subscriptions
           SET renewal_mode = 'same_day'
           WHERE payment_type = 'subscription'
             AND (renewal_mode IS NULL OR renewal_mode = '')"""
    )
    conn.execute(
        """UPDATE subscriptions
           SET renewal_interval = CASE billing_cycle
                WHEN '月付' THEN 1
                WHEN '季付' THEN 3
                WHEN '年付' THEN 12
                WHEN '自定义' THEN COALESCE(billing_interval_months, 1)
                ELSE 1 END
           WHERE payment_type = 'subscription'
             AND renewal_interval IS NULL"""
    )
    conn.execute(
        """UPDATE subscriptions
           SET renewal_anchor_day = CAST(
               SUBSTR(COALESCE(start_date, next_renewal_date), 9, 2) AS INTEGER
           )
           WHERE payment_type = 'subscription'
             AND renewal_anchor_day IS NULL
             AND COALESCE(start_date, next_renewal_date) IS NOT NULL"""
    )


def _ensure_planned_expense_columns(conn):
    conn.execute(
        """CREATE TABLE IF NOT EXISTS planned_expenses (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            description  TEXT NOT NULL,
            amount       REAL NOT NULL,
            amount_cents INTEGER,
            due_date     TEXT,
            category     TEXT,
            subcategory  TEXT,
            notes        TEXT,
            subscription_id INTEGER,
            transaction_id  INTEGER,
            status       TEXT NOT NULL DEFAULT 'open',
            created_at   TEXT DEFAULT (datetime('now', 'localtime'))
        )"""
    )


def _ensure_batch_submission_schema(conn):
    conn.execute(
        """CREATE TABLE IF NOT EXISTS batch_submissions (
            submission_id TEXT PRIMARY KEY,
            payload_hash TEXT NOT NULL,
            record_count INTEGER NOT NULL,
            created_at   TEXT DEFAULT (datetime('now', 'localtime'))
        )"""
    )


def _ensure_idempotency_schema(conn):
    conn.execute(
        """CREATE TABLE IF NOT EXISTS idempotency_keys (
            idempotency_key TEXT PRIMARY KEY,
            operation TEXT NOT NULL,
            payload_hash TEXT NOT NULL,
            response_json TEXT,
            created_at TEXT NOT NULL
        )"""
    )


def _migrate_amortized_to_subscriptions(conn):
    """One-time migration: create prepaid recurring_cost entries for transactions
    that already have amortization_months set but no linked subscription entry."""
    rows = conn.execute("""
        SELECT t.* FROM transactions t
        WHERE t.amortization_months > 1
          AND NOT EXISTS (
              SELECT 1 FROM subscriptions s WHERE s.transaction_id = t.id
          )
    """).fetchall()

    for row in rows:
        item = dict(row)
        amount = float(item.get("amount") or 0)
        amount_cents = int(round(amount * 100))
        months = int(float(item.get("amortization_months") or 1))
        start = item.get("amortization_start") or item.get("date")
        conn.execute(
            """INSERT INTO subscriptions
               (name, amount, amount_cents, billing_cycle, billing_interval_months,
                start_date, category, subcategory, payment_type, transaction_id,
                auto_renew, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'prepaid', ?, 0, 'active')""",
            (
                item["description"],
                amount,
                amount_cents,
                SUBSCRIPTION_CYCLE_ONE_TIME,
                months,
                start,
                item.get("category"),
                item.get("subcategory"),
                item["id"],
            ),
        )


def _ensure_query_indexes(conn):
    """Keep common ledger and relationship lookups indexed on both backends."""
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
        conn.execute(statement)


def _ensure_subscription_amount_cents(conn):
    columns = _table_columns(conn, "subscriptions")
    if "amount_cents" not in columns:
        conn.execute("ALTER TABLE subscriptions ADD COLUMN amount_cents INTEGER")
    conn.execute(
        """UPDATE subscriptions
           SET amount_cents = CAST(ROUND(amount * 100) AS INTEGER)
           WHERE amount_cents IS NULL AND amount IS NOT NULL"""
    )


def _init_budgets(conn):
    """Simplify the unshipped category-budget schema to monthly total targets."""
    columns = _table_columns(conn, "budgets")
    if "scope" in columns:
        legacy_rows = conn.execute(
            """SELECT month, amortized_budget_cents, cash_budget_cents
               FROM budgets WHERE scope = 'overall'"""
        ).fetchall()
        conn.execute("DROP TABLE budgets")
        _create_budgets_table(conn)
        for row in legacy_rows:
            conn.execute(
                """INSERT INTO budgets
                   (month, amortized_budget_cents, cash_budget_cents)
                   VALUES (?, ?, ?)""",
                (
                    row["month"],
                    row["amortized_budget_cents"],
                    row["cash_budget_cents"],
                ),
            )
        return
    _create_budgets_table(conn)
