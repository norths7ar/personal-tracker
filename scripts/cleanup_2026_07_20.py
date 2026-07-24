import argparse
import sys
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.constants import SUBSCRIPTION_CYCLE_ONE_TIME
from core.db import get_database_url


def _fetch_one(cur, sql: str) -> dict:
    cur.execute(sql)
    return dict(cur.fetchone())


def _column_exists(cur, table: str, column: str) -> bool:
    cur.execute(
        """SELECT 1
           FROM information_schema.columns
           WHERE table_schema = 'public'
             AND table_name = %s
             AND column_name = %s""",
        (table, column),
    )
    return cur.fetchone() is not None


def _print_plan(cur) -> dict:
    columns = {
        "status": _column_exists(cur, "transactions", "status"),
        "void_reason": _column_exists(cur, "transactions", "void_reason"),
    }
    counts = _fetch_one(
        cur,
        "SELECT COUNT(*) AS legacy_one_time FROM subscriptions WHERE billing_cycle = 'one_time'",
    )
    if columns["status"]:
        counts.update(
            _fetch_one(
                cur,
                "SELECT COUNT(*) AS status_voided FROM transactions WHERE status = 'voided'",
            )
        )
    else:
        counts["status_voided"] = 0
    if columns["void_reason"]:
        counts.update(
            _fetch_one(
                cur,
                """SELECT COUNT(*) AS void_reason_nonempty
                   FROM transactions
                   WHERE void_reason IS NOT NULL AND void_reason <> ''""",
            )
        )
    else:
        counts["void_reason_nonempty"] = 0

    print("Cleanup plan:")
    print(f"- subscriptions.billing_cycle one_time rows: {counts['legacy_one_time']}")
    print(f"- transactions.status column exists: {columns['status']}")
    print(f"- transactions.void_reason column exists: {columns['void_reason']}")
    print(f"- transactions status='voided' rows: {counts['status_voided']}")
    print(
        f"- transactions non-empty void_reason rows: {counts['void_reason_nonempty']}"
    )
    print()
    print("Actions when --apply is set:")
    print(
        f"- UPDATE subscriptions billing_cycle 'one_time' -> '{SUBSCRIPTION_CYCLE_ONE_TIME}'"
    )
    print("- DROP transactions.status if present")
    print("- DROP transactions.void_reason if present")

    return {**counts, **columns}


def _apply_cleanup(cur, plan: dict) -> None:
    if plan["status_voided"] or plan["void_reason_nonempty"]:
        raise RuntimeError(
            "Refusing to drop transactions.status/void_reason because voided data still exists."
        )

    cur.execute(
        "UPDATE subscriptions SET billing_cycle = %s WHERE billing_cycle = 'one_time'",
        (SUBSCRIPTION_CYCLE_ONE_TIME,),
    )
    if plan["status"]:
        cur.execute("ALTER TABLE transactions DROP COLUMN status")
    if plan["void_reason"]:
        cur.execute("ALTER TABLE transactions DROP COLUMN void_reason")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="One-time cleanup for legacy subscription and transaction schema values."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the cleanup. Without this flag, only prints the plan.",
    )
    args = parser.parse_args()

    with psycopg.connect(
        get_database_url(), row_factory=dict_row, prepare_threshold=None
    ) as conn:
        with conn.cursor() as cur:
            plan = _print_plan(cur)
            if not args.apply:
                print()
                print("Dry run only. Re-run with --apply to modify the database.")
                return 0

            _apply_cleanup(cur, plan)
        conn.commit()

    print()
    print("Cleanup applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
