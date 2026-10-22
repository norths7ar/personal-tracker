import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from scripts import backup_sqlite


class SQLiteBackupTest(unittest.TestCase):
    def test_corrupt_source_preserves_snapshots_and_cleans_partial_backup(self):
        """源库损坏时不执行保留清理，已有快照逐字节不变且无残留文件。"""
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)
            source = temporary_path / "source.db"
            destination_directory = temporary_path / "backups"
            with closing(sqlite3.connect(source)) as connection:
                connection.execute("CREATE TABLE entries (value TEXT NOT NULL)")
                connection.execute("INSERT INTO entries VALUES ('preserved')")
                connection.commit()

            snapshots = [
                backup_sqlite.create_backup(source, destination_directory, keep=2)
                for _ in range(2)
            ]
            before = {path.name: path.read_bytes() for path in snapshots}
            self.assertEqual(len(before), 2)
            source.write_bytes(b"not a SQLite database")

            with self.assertRaises(sqlite3.DatabaseError):
                backup_sqlite.create_backup(source, destination_directory, keep=1)

            self.assertEqual(
                {
                    path.name: path.read_bytes()
                    for path in destination_directory.iterdir()
                },
                before,
            )

    def test_creates_valid_snapshot_and_enforces_retention(self):
        """备份可打开且保留原数据，新快照成功后才淘汰旧快照。"""
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
