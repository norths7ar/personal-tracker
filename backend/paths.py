import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def data_directory() -> Path:
    # The launcher may select an isolated instance; this is not an app setting.
    value = os.environ.get("TRACKER_DATA_DIR")
    return Path(value).expanduser().resolve() if value else PROJECT_ROOT / "data"


def database_path() -> Path:
    return data_directory() / "tracker.db"


def jobs_database_path() -> Path:
    return data_directory() / "jobs.db"
