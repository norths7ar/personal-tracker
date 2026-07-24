from pathlib import Path

import yaml

_CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"


def load_config() -> dict:
    with _CONFIG_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def config_version() -> int:
    return _CONFIG_PATH.stat().st_mtime_ns
