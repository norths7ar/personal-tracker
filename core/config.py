"""Instance paths and the configuration consumed by record extraction."""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from core.llm import LLMConfig
from core.settings_models import StoredSettings

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
    return _extraction_config(settings)


def _extraction_config(settings: StoredSettings) -> dict:
    return {
        **settings.records.categories,
        "llm": settings.model.model_dump(),
        "diet": {"meal_types": settings.records.meal_types},
    }


@dataclass(frozen=True)
class ExtractionSnapshot:
    """Private request configuration, detached from all mutable settings objects."""

    llm: LLMConfig
    api_key: str = field(repr=False)
    _config_json: str = field(repr=False)

    def extraction_config(self) -> dict:
        return json.loads(self._config_json)


def load_extraction_snapshot() -> ExtractionSnapshot:
    from core.settings_store import decrypt_secret, read_settings

    _, settings = read_settings()
    model = settings.model
    return ExtractionSnapshot(
        llm=LLMConfig(
            protocol=model.protocol,
            base_url=model.base_url,
            model=model.model,
            temperature=model.temperature,
            max_tokens=model.max_tokens,
            timeout=model.timeout,
            thinking=model.thinking,
        ),
        api_key=decrypt_secret(settings.api_key_encrypted),
        _config_json=json.dumps(_extraction_config(settings)),
    )
