import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from scripts import backup_sqlite


class SQLiteBackupTest(unittest.TestCase):
    def test_corrupt_source_preserves_snapshots_and_cleans_partial_backup(self):
        """源库损坏时不执行保留清理，已有快照逐字节不变且无残留文件。"""
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)
            source = temporary_path / "tracker.db"
            destination_directory = temporary_path / "backups"
            with closing(sqlite3.connect(source)) as connection:
                connection.execute("CREATE TABLE entries (value TEXT NOT NULL)")
                connection.execute("INSERT INTO entries VALUES ('preserved')")
                connection.commit()

            snapshots = [
                backup_sqlite.create_backup(source, destination_directory, keep=2) for _ in range(2)
            ]
            before = {path.name: path.read_bytes() for path in snapshots}
            self.assertEqual(len(before), 2)
            source.write_bytes(b"not a SQLite database")

            with self.assertRaises(sqlite3.DatabaseError):
                backup_sqlite.create_backup(source, destination_directory, keep=1)

            self.assertEqual(
                {path.name: path.read_bytes() for path in destination_directory.iterdir()},
                before,
            )

    def test_creates_valid_snapshot_and_enforces_retention(self):
        """默认备份两库，各自保留有效快照，清理旧快照不误删另一库。"""
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)
            destination_directory = temporary_path / "backups" / "rolling"
            for name in ("tracker", "jobs"):
                with closing(sqlite3.connect(temporary_path / f"{name}.db")) as connection:
                    connection.execute("CREATE TABLE entries (value TEXT NOT NULL)")
                    connection.execute("INSERT INTO entries VALUES (?)", (name,))
                    connection.commit()

            with (
                patch.dict(os.environ, {"TRACKER_DATA_DIR": str(temporary_path)}),
                patch("sys.argv", ["backup_sqlite", "--keep", "1"]),
            ):
                backup_sqlite.main()

            snapshots = {
                name: next(destination_directory.glob(f"{name}-*.db"))
                for name in ("tracker", "jobs")
            }
            for name, other in (("tracker", "jobs"), ("jobs", "tracker")):
                other_bytes = snapshots[other].read_bytes()
                first_snapshot = snapshots[name]
                snapshots[name] = backup_sqlite.create_backup(
                    temporary_path / f"{name}.db", destination_directory, keep=1
                )
                self.assertFalse(first_snapshot.exists())
                self.assertEqual(snapshots[other].read_bytes(), other_bytes)
                self.assertEqual(len(list(destination_directory.glob(f"{name}-*.db"))), 1)

            for name, snapshot in snapshots.items():
                with closing(sqlite3.connect(snapshot)) as connection:
                    self.assertEqual(
                        connection.execute("PRAGMA integrity_check").fetchone(), ("ok",)
                    )
                    self.assertEqual(
                        connection.execute("SELECT value FROM entries").fetchone(), (name,)
                    )
