"""Instance paths and the configuration consumed by record extraction."""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def data_directory() -> Path:
    # The launcher may select an isolated instance; this is not an app setting.
    value = os.environ.get("TRACKER_DATA_DIR")
    return Path(value).expanduser().resolve() if value else PROJECT_ROOT / "data"


def database_path() -> Path:
    return data_directory() / "expenses.db"


def load_config() -> dict:
    from core.settings_store import read_settings

    _, settings = read_settings()
    return {
        **settings.records.categories,
        "llm": settings.model.model_dump(),
        "diet": {"meal_types": settings.records.meal_types},
    }


def config_version() -> str:
    from core.settings_store import read_settings

    revision, _ = read_settings()
    return revision
