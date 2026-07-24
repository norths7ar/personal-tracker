import importlib.util
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).parent.parent
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "backup_cloud_to_sqlite.py"
SPEC = importlib.util.spec_from_file_location("backup_cloud_to_sqlite", SCRIPT_PATH)
backup_script = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(backup_script)


class CloudBackupScriptTest(unittest.TestCase):
    def test_snapshot_initialization_has_all_application_tables(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            snapshot_path = Path(temporary_directory) / "snapshot.db"
            connection = backup_script.initialize_snapshot(snapshot_path)
            connection.close()

            with closing(sqlite3.connect(snapshot_path)) as verification_connection:
                tables = {
                    row[0]
                    for row in verification_connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                }
            self.assertTrue(set(backup_script.BACKUP_TABLES).issubset(tables))

    def test_prune_backups_keeps_the_newest_snapshots(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_dir = Path(temporary_directory)
            for day in range(1, 5):
                (output_dir / f"cloud-2026070{day}-000000.db").touch()

            backup_script.prune_backups(output_dir, keep=2)

            remaining = sorted(path.name for path in output_dir.glob("cloud-*.db"))
            self.assertEqual(
                remaining,
                ["cloud-20260703-000000.db", "cloud-20260704-000000.db"],
            )

    def test_missing_cloud_table_is_kept_empty_in_snapshot(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            snapshot_path = Path(temporary_directory) / "snapshot.db"
            local_connection = backup_script.initialize_snapshot(snapshot_path)
            try:
                with patch.object(backup_script, "postgres_columns", return_value=[]):
                    copied_rows = backup_script.copy_table(
                        object(), local_connection, "budgets"
                    )
                count = local_connection.execute(
                    "SELECT COUNT(*) FROM budgets"
                ).fetchone()[0]
            finally:
                local_connection.close()

            self.assertEqual(copied_rows, 0)
            self.assertEqual(count, 0)
