import argparse
import re
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

from backend.paths import data_directory, database_path, jobs_database_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a consistent SQLite backup and retain recent snapshots."
    )
    parser.add_argument(
        "--source",
        type=Path,
        help="Back up only this database; defaults to tracker.db and jobs.db.",
    )
    parser.add_argument(
        "--destination-dir", type=Path, default=data_directory() / "backups" / "rolling"
    )
    parser.add_argument("--keep", type=int, default=30, help="Snapshots to retain per database.")
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
    prefix = source.stem
    destination = destination_dir / f"{prefix}-{timestamp}.db"
    temporary = destination.with_suffix(".tmp")

    try:
        with (
            closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as source_connection,
            closing(sqlite3.connect(temporary)) as destination_connection,
        ):
            source_connection.backup(destination_connection)
            integrity_result = destination_connection.execute("PRAGMA integrity_check").fetchone()
            foreign_key_errors = destination_connection.execute(
                "PRAGMA foreign_key_check"
            ).fetchall()

        if integrity_result != ("ok",):
            raise RuntimeError(f"Backup integrity check failed: {integrity_result}")
        if foreign_key_errors:
            raise RuntimeError(
                f"Backup foreign key check failed with {len(foreign_key_errors)} row(s)"
            )
        temporary.replace(destination)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise

    snapshot_name = re.compile(rf"{re.escape(prefix)}-\d{{8}}-\d{{6}}-\d{{6}}\.db")
    snapshots = sorted(
        path
        for path in destination_dir.iterdir()
        if path.is_file() and snapshot_name.fullmatch(path.name)
    )
    for stale_snapshot in snapshots[:-keep]:
        stale_snapshot.unlink()

    return destination


def main() -> None:
    args = parse_args()
    sources = [args.source] if args.source is not None else [database_path()]
    if args.source is None:
        jobs_source = jobs_database_path()
        if jobs_source.exists():
            sources.append(jobs_source)
        else:
            print(f"Skipped uninitialized jobs database: {jobs_source}")
    for source in sources:
        destination = create_backup(source, args.destination_dir, args.keep)
        print(f"Created SQLite backup: {destination}")


if __name__ == "__main__":
    main()
