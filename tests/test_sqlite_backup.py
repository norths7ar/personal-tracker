import importlib.util
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "backup_sqlite.py"
SPEC = importlib.util.spec_from_file_location("backup_sqlite", SCRIPT_PATH)
backup_sqlite = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(backup_sqlite)


class SQLiteBackupTest(unittest.TestCase):
    def test_creates_valid_snapshot_and_enforces_retention(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)
            source = temporary_path / "source.db"
            destination_directory = temporary_path / "backups"

            with closing(sqlite3.connect(source)) as connection:
                connection.execute("CREATE TABLE entries (value TEXT NOT NULL)")
                connection.execute("INSERT INTO entries VALUES ('preserved')")
                connection.commit()

            first_snapshot = backup_sqlite.create_backup(
                source, destination_directory, keep=1
            )
            second_snapshot = backup_sqlite.create_backup(
                source, destination_directory, keep=1
            )

            self.assertFalse(first_snapshot.exists())
            self.assertTrue(second_snapshot.is_file())
            self.assertEqual(len(list(destination_directory.glob("expenses-*.db"))), 1)
            with closing(sqlite3.connect(second_snapshot)) as connection:
                self.assertEqual(
                    connection.execute("PRAGMA integrity_check").fetchone(), ("ok",)
                )
                self.assertEqual(
                    connection.execute("SELECT value FROM entries").fetchone(),
                    ("preserved",),
                )

    def test_rejects_an_invalid_retention_count(self):
        with self.assertRaisesRegex(ValueError, "at least 1"):
            backup_sqlite.create_backup(Path("missing.db"), Path("backups"), keep=0)
