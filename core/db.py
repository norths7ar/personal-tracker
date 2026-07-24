import sqlite3
from contextlib import closing
from pathlib import Path
from urllib.parse import quote

from core.constants import SUBSCRIPTION_CYCLE_ONE_TIME, TRANSACTION_TYPE_SQL_LIST
from core.secrets import get_secret

DB_PATH = Path(__file__).parent.parent / "data" / "expenses.db"


class DatabaseConfigError(RuntimeError):
    pass


class Connection:
    def __init__(self, conn, backend: str):
        self._conn = conn
        self.backend = backend

    def execute(self, sql: str, params=None):
        params = [] if params is None else params
        return self._conn.execute(self._prepare(sql), params)

    def executemany(self, sql: str, params):
        prepared = self._prepare(sql)
        if self.backend == "postgres":
            with self._conn.cursor() as cursor:
                cursor.executemany(prepared, params)
            return
        return self._conn.executemany(prepared, params)

    def commit(self):
        return self._conn.commit()

    def rollback(self):
        return self._conn.rollback()

    def close(self):
        return self._conn.close()

    def _prepare(self, sql: str) -> str:
        if self.backend == "postgres":
            return sql.replace("?", "%s")
        return sql


def get_backend() -> str:
    return (get_secret("DB_BACKEND", "sqlite") or "sqlite").strip().lower()


def get_database_url() -> str:
    database_url = get_secret("DATABASE_URL")
    if database_url:
        return database_url

    project_ref = get_secret("SUPABASE_PROJECT_REF")
    project_password = get_secret("SUPABASE_PROJECT_PASSWORD")
    pooler_host = get_secret("SUPABASE_POOLER_HOST")
    if project_ref and project_password and pooler_host:
        password = quote(project_password, safe="")
        return f"postgresql://postgres.{project_ref}:{password}@{pooler_host}:6543/postgres"

    raise DatabaseConfigError(
        "PostgreSQL backend requires DATABASE_URL, or SUPABASE_PROJECT_REF, "
        "SUPABASE_PROJECT_PASSWORD, and SUPABASE_POOLER_HOST."
    )


def _connect_sqlite():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _connect_postgres():
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:
        raise DatabaseConfigError(
            "PostgreSQL backend requires psycopg. Install requirements.txt first."
        ) from exc

    conn = psycopg.connect(
        get_database_url(), row_factory=dict_row, prepare_threshold=None
    )
    return conn


def _connect():
    backend = get_backend()
    if backend == "sqlite":
        return Connection(_connect_sqlite(), backend)
    if backend in {"postgres", "postgresql"}:
        return Connection(_connect_postgres(), "postgres")
    raise DatabaseConfigError(f"Unsupported DB_BACKEND: {backend}")


def is_postgres() -> bool:
    return get_backend() in {"postgres", "postgresql"}


def returning_id_clause() -> str:
    return " RETURNING id" if is_postgres() else ""


def to_cents(amount) -> int:
    return int(round(float(amount) * 100))


def inserted_id(cursor) -> int:
    if is_postgres():
        row = cursor.fetchone()
        return int(row["id"])
    return cursor.lastrowid


def placeholders(count: int) -> str:
    return ",".join("?" * count)


def init_db():
    with closing(_connect()) as conn:
        if conn.backend == "postgres":
            _init_postgres(conn)
        else:
            _init_sqlite(conn)

        _ensure_transaction_amount_cents(conn)
        _ensure_transaction_workflow_columns(conn)
        _ensure_subscription_amount_cents(conn)
        _ensure_subscription_payment_type(conn)
        _ensure_subscription_renewal_columns(conn)
        _ensure_planned_expense_columns(conn)
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

def _init_postgres(conn):
    conn.execute(f"""
    CREATE TABLE IF NOT EXISTS transactions (
        id          INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
        type        TEXT NOT NULL CHECK(type IN ({TRANSACTION_TYPE_SQL_LIST})),
        description TEXT NOT NULL,
        amount      DOUBLE PRECISION NOT NULL,
        amount_cents INTEGER,
        date        TEXT NOT NULL,
        category    TEXT,
        subcategory TEXT,
        notes       TEXT,
        confidence  DOUBLE PRECISION,
        subscription_id INTEGER,
        created_at  TEXT DEFAULT to_char(now(), 'YYYY-MM-DD HH24:MI:SS')
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS diet_meals (
        id          INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
        date        TEXT NOT NULL,
        time        TEXT,
        meal_type   TEXT,
        description TEXT NOT NULL,
        notes       TEXT,
        confidence  DOUBLE PRECISION,
        created_at  TEXT DEFAULT to_char(now(), 'YYYY-MM-DD HH24:MI:SS')
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS diet_foods (
        id          INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
        meal_id     INTEGER NOT NULL REFERENCES diet_meals(id) ON DELETE CASCADE,
        food_name   TEXT NOT NULL,
        quantity    TEXT
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS subscriptions (
        id                 INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
        name               TEXT NOT NULL,
        vendor             TEXT,
        amount             DOUBLE PRECISION NOT NULL,
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
        created_at         TEXT DEFAULT to_char(now(), 'YYYY-MM-DD HH24:MI:SS')
    )
    """)

def _create_budgets_table(conn):
    """Store monthly targets separately from immutable transaction facts."""
    conn.execute(
        f"""CREATE TABLE IF NOT EXISTS budgets (
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
    if conn.backend == "postgres":
        rows = conn.execute(
            """SELECT column_name FROM information_schema.columns
               WHERE table_name = 'transactions' AND table_schema = 'public'"""
        ).fetchall()
        return {row["column_name"] for row in rows}
    return {
        row["name"]
        for row in conn.execute("PRAGMA table_info(transactions)").fetchall()
    }


def _table_columns(conn, table_name: str) -> set[str]:
    if conn.backend == "postgres":
        rows = conn.execute(
            """SELECT column_name FROM information_schema.columns
               WHERE table_name = ? AND table_schema = 'public'""",
            (table_name,),
        ).fetchall()
        return {row["column_name"] for row in rows}
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
    }
    for name, definition in additions.items():
        if name not in columns:
            conn.execute(f"ALTER TABLE transactions ADD COLUMN {name} {definition}")



def _ensure_subscription_payment_type(conn):
    columns = _table_columns(conn, "subscriptions")
    if "payment_type" not in columns:
        conn.execute("ALTER TABLE subscriptions ADD COLUMN payment_type TEXT DEFAULT 'subscription'")
        conn.execute("UPDATE subscriptions SET payment_type = 'subscription' WHERE payment_type IS NULL")
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
           SET renewal_anchor_day = CAST(SUBSTR(COALESCE(start_date, next_renewal_date), 9, 2) AS INTEGER)
           WHERE payment_type = 'subscription'
             AND renewal_anchor_day IS NULL
             AND COALESCE(start_date, next_renewal_date) IS NOT NULL"""
    )


def _ensure_planned_expense_columns(conn):
    if conn.backend == "postgres":
        id_column = "INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY"
        created_at = "TEXT DEFAULT to_char(now(), 'YYYY-MM-DD HH24:MI:SS')"
    else:
        id_column = "INTEGER PRIMARY KEY AUTOINCREMENT"
        created_at = "TEXT DEFAULT (datetime('now', 'localtime'))"
    conn.execute(
        f"""CREATE TABLE IF NOT EXISTS planned_expenses (
            id           {id_column},
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
            created_at   {created_at}
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
