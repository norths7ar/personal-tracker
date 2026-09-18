from pathlib import Path

import yaml

from core.secrets import get_secret

_CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"


def database_path() -> Path:
    path = Path(get_secret("DATABASE_PATH", "data/expenses.db")).expanduser()
    return path if path.is_absolute() else _CONFIG_PATH.parent / path


def load_config() -> dict:
    with _CONFIG_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def config_version() -> int:
    return _CONFIG_PATH.stat().st_mtime_ns
