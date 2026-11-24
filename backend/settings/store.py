"""Independent SQLite settings store with atomic updates and encrypted credentials."""

import hashlib
import hmac
import json
import secrets
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass, field
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken

from backend.capture.batch import DEFAULT_BATCH_BLOCKS, DEFAULT_BATCH_FINANCE_EVENTS
from backend.db import connect
from backend.diet.extractor import DEFAULT_DIET_EXTRACTOR
from backend.jobs.prompts import DEFAULT_JOB_EXTRACTOR, DEFAULT_JOB_MATCHER
from backend.ledger.classifier import DEFAULT_EXPENSE_CLASSIFIER
from backend.llm import LLMConfig
from backend.paths import data_directory, database_path
from backend.settings.models import (
    DEFAULT_SETTINGS,
    PROMPT_PLACEHOLDERS,
    AccessSettings,
    PromptValues,
    SettingsResponse,
    StoredSettings,
)


class SettingsConflict(ValueError):
    pass


def default_settings() -> StoredSettings:
    return StoredSettings.model_validate(DEFAULT_SETTINGS)


def _cipher() -> Fernet:
    try:
        return Fernet((data_directory() / ".key").read_bytes().strip())
    except (OSError, ValueError) as exc:
        raise RuntimeError("设置加密密钥缺失或损坏，请恢复 data/.key，不要重新生成") from exc


def encrypt_secret(value: str) -> str:
    return _cipher().encrypt(value.encode()).decode() if value else ""


def decrypt_secret(value: str) -> str:
    if not value:
        return ""
    try:
        return _cipher().decrypt(value.encode()).decode()
    except InvalidToken as exc:
        raise RuntimeError("设置密钥不匹配，请同时恢复 settings.db 与 .key") from exc


def initialize_settings(initial: StoredSettings | None = None) -> None:
    directory = data_directory()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "settings.db"
    if path.exists():
        # Never silently replace a lost key or overwrite existing configuration.
        _cipher()
        _, settings = read_settings()
        decrypt_secret(settings.signing_key_encrypted)
        decrypt_secret(settings.api_key_encrypted)
        if initial is not None:
            raise ValueError("设置已经存在，不能重复导入")
        return
    key_path = directory / ".key"
    if key_path.exists() or database_path().exists():
        raise RuntimeError("已有实例的设置库缺失，请恢复 settings.db，不会重置访问控制")
    try:
        with key_path.open("xb") as key_file:
            key_file.write(Fernet.generate_key())
    except FileExistsError:
        _cipher()
    settings = (initial or default_settings()).model_copy(deep=True)
    if not settings.signing_key_encrypted:
        settings.signing_key_encrypted = encrypt_secret(secrets.token_urlsafe(48))
    with closing(connect(path)) as connection, connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS settings "
            "(id INTEGER PRIMARY KEY CHECK (id = 1), revision TEXT NOT NULL, "
            "document TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT OR IGNORE INTO settings VALUES (1, ?, ?)",
            (uuid4().hex, settings.model_dump_json()),
        )


def read_settings() -> tuple[str, StoredSettings]:
    path = data_directory() / "settings.db"
    if not path.exists():
        if (data_directory() / ".key").exists() or database_path().exists():
            raise RuntimeError("已有实例的设置库缺失，请恢复 settings.db")
        # Importing modules and generating OpenAPI must not write private data.
        return "uninitialized", default_settings()
    with closing(connect(path, readonly=True)) as connection:
        row = connection.execute("SELECT revision, document FROM settings WHERE id = 1").fetchone()
    if row is None:
        raise RuntimeError("设置存储不完整，请从备份恢复")
    return row[0], StoredSettings.model_validate_json(row[1])


def update_settings(revision: str, change: Callable[[StoredSettings], None]) -> SettingsResponse:
    path = data_directory() / "settings.db"
    with closing(connect(path)) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        current, document = connection.execute(
            "SELECT revision, document FROM settings WHERE id = 1"
        ).fetchone()
        if current != revision:
            raise SettingsConflict("设置已在其他页面修改，请重新载入后再保存")
        settings = StoredSettings.model_validate_json(document)
        change(settings)
        settings = StoredSettings.model_validate(settings.model_dump())
        new_revision = uuid4().hex
        connection.execute(
            "UPDATE settings SET revision = ?, document = ? WHERE id = 1",
            (new_revision, settings.model_dump_json()),
        )
    return public_settings(new_revision, settings)


def public_settings(
    revision: str | None = None, settings: StoredSettings | None = None
) -> SettingsResponse:
    if settings is None:
        revision, settings = read_settings()
    return SettingsResponse(
        revision=revision,
        model=settings.model,
        records=settings.records,
        prompts=public_prompts(settings),
        access=AccessSettings(
            enabled=settings.access.enabled,
            password_configured=bool(settings.access.password_hash),
            cookie_secure=settings.access.cookie_secure,
            session_seconds=settings.access.session_seconds,
        ),
        api_key_configured=bool(settings.api_key_encrypted),
        data_directory=str(data_directory()),
        database_path=str(database_path()),
    )


def hash_password(value: str) -> str:
    if not value:
        return ""
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(value.encode(), salt=salt, n=16384, r=8, p=1)
    return f"{salt.hex()}:{digest.hex()}"


def verify_password(value: str, stored: str) -> bool:
    if not stored:
        return False
    salt, expected = stored.split(":", 1)
    digest = hashlib.scrypt(value.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1)
    return hmac.compare_digest(digest.hex(), expected)


def load_config() -> dict:

    _, settings = read_settings()
    return _extraction_config(settings)


def _extraction_config(settings: StoredSettings) -> dict:
    return {
        **settings.records.categories,
        "llm": settings.model.model_dump(),
        "diet": {"meal_types": settings.records.meal_types},
        "prompts": effective_prompts(settings),
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


PROMPT_DEFAULTS = {
    "expense_classifier": DEFAULT_EXPENSE_CLASSIFIER,
    "diet_extractor": DEFAULT_DIET_EXTRACTOR,
    "batch_blocks": DEFAULT_BATCH_BLOCKS,
    "batch_finance_events": DEFAULT_BATCH_FINANCE_EVENTS,
    "job_extractor": DEFAULT_JOB_EXTRACTOR,
    "job_matcher": DEFAULT_JOB_MATCHER,
}


def effective_prompts(settings: StoredSettings) -> dict[str, str]:
    return {
        name: override if override is not None else PROMPT_DEFAULTS[name]
        for name, override in settings.prompts.model_dump().items()
    }


def public_prompts(settings: StoredSettings) -> PromptValues:
    effective = effective_prompts(settings)
    return PromptValues.model_validate(
        {
            name: {
                "text": effective[name],
                "customized": override is not None,
                "required_placeholders": list(PROMPT_PLACEHOLDERS[name]),
            }
            for name, override in settings.prompts.model_dump().items()
        }
    )
