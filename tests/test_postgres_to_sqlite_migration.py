import importlib.util
import sqlite3
import sys
import unittest
from pathlib import Path

SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "migrate_postgres_to_sqlite.py"
SPEC = importlib.util.spec_from_file_location(
    "postgres_to_sqlite_migration", SCRIPT_PATH
)
assert SPEC and SPEC.loader
migration = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = migration
SPEC.loader.exec_module(migration)


class PostgresToSqliteMigrationTest(unittest.TestCase):
    def test_copy_table_preserves_columns_rows_and_ids(self):
        source = sqlite3.connect(":memory:")
        target = sqlite3.connect(":memory:")
        try:
            source.execute(
                "CREATE TABLE transactions "
                "(id INTEGER PRIMARY KEY, description TEXT, amount REAL)"
            )
            source.executemany(
                "INSERT INTO transactions (id, description, amount) VALUES (?, ?, ?)",
                [(4, "早餐", 12.5), (9, "地铁", 3.0)],
            )
            target.row_factory = sqlite3.Row
            target.execute(
                "CREATE TABLE transactions "
                "(id INTEGER PRIMARY KEY, description TEXT, amount REAL, extra TEXT)"
            )

            copied = migration.copy_table(source, target, "transactions")

            self.assertEqual(copied, 2)
            rows = target.execute(
                "SELECT id, description, amount, extra FROM transactions ORDER BY id"
            ).fetchall()
            self.assertEqual(
                [tuple(row) for row in rows],
                [(4, "早餐", 12.5, None), (9, "地铁", 3.0, None)],
            )
        finally:
            source.close()
            target.close()


if __name__ == "__main__":
    unittest.main()
