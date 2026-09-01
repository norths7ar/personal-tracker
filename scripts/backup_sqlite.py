from __future__ import annotations

import argparse
import os
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = PROJECT_ROOT / "data" / "expenses.db"
DEFAULT_DESTINATION = PROJECT_ROOT / "data" / "backup" / "rolling"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a consistent SQLite backup and retain recent snapshots."
    )
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--destination-dir", type=Path, default=DEFAULT_DESTINATION)
    parser.add_argument("--keep", type=int, default=30)
    return parser.parse_args()


def create_backup(source: Path, destination_dir: Path, keep: int) -> Path:
    if keep < 1:
        raise ValueError("--keep must be at least 1")

    source = source.resolve()
    destination_dir = destination_dir.resolve()
    if not source.is_file():
        raise FileNotFoundError(f"SQLite database does not exist: {source}")

    destination_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    destination = destination_dir / f"expenses-{timestamp}.db"
    temporary = destination.with_suffix(".tmp")

    try:
        with (
            closing(sqlite3.connect(source)) as source_connection,
            closing(sqlite3.connect(temporary)) as destination_connection,
        ):
            source_connection.backup(destination_connection)
            integrity_result = destination_connection.execute(
                "PRAGMA integrity_check"
            ).fetchone()
            foreign_key_errors = destination_connection.execute(
                "PRAGMA foreign_key_check"
            ).fetchall()

        if integrity_result != ("ok",):
            raise RuntimeError(f"Backup integrity check failed: {integrity_result}")
        if foreign_key_errors:
            raise RuntimeError(
                f"Backup foreign key check failed with {len(foreign_key_errors)} row(s)"
            )
        os.replace(temporary, destination)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise

    snapshots = sorted(
        path for path in destination_dir.glob("expenses-*.db") if path.is_file()
    )
    for stale_snapshot in snapshots[:-keep]:
        stale_snapshot.unlink()

    return destination


def main() -> None:
    args = parse_args()
    destination = create_backup(args.source, args.destination_dir, args.keep)
    print(f"Created SQLite backup: {destination}")


if __name__ == "__main__":
    main()
