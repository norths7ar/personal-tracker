"""Independent SQLite settings store with atomic updates and encrypted credentials."""

import hashlib
import hmac
import json
import secrets
import sqlite3
from collections.abc import Callable
from contextlib import closing
from pathlib import Path
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken

from core.config import data_directory, database_path
from core.settings_models import AccessSettings, SettingsResponse, StoredSettings


class SettingsConflict(ValueError):
    pass


def default_settings() -> StoredSettings:
    path = Path(__file__).with_name("default_settings.json")
    return StoredSettings.model_validate(json.loads(path.read_text(encoding="utf-8")))


def _cipher() -> Fernet:
    try:
        return Fernet((data_directory() / ".key").read_bytes().strip())
    except (OSError, ValueError) as exc:
        raise RuntimeError(
            "设置加密密钥缺失或损坏，请恢复 data/.key，不要重新生成"
        ) from exc


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
    with closing(sqlite3.connect(path)) as connection, connection:
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
    with closing(sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)) as connection:
        row = connection.execute(
            "SELECT revision, document FROM settings WHERE id = 1"
        ).fetchone()
    if row is None:
        raise RuntimeError("设置存储不完整，请从备份恢复")
    return row[0], StoredSettings.model_validate_json(row[1])


def update_settings(
    revision: str, change: Callable[[StoredSettings], None]
) -> SettingsResponse:
    path = data_directory() / "settings.db"
    with closing(sqlite3.connect(path)) as connection, connection:
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
