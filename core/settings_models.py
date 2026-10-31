"""Validated application settings; secrets never appear in public responses."""

from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

from core.constants import TRANSACTION_TYPES


class SettingsModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class ModelSettings(SettingsModel):
    base_url: str = Field(min_length=1)
    model: str = Field(min_length=1)
    temperature: float = Field(ge=0, le=2)
    max_tokens: int = Field(gt=0)
    timeout: float = Field(gt=0)
    confidence_threshold: float = Field(ge=0, le=1)

    @field_validator("base_url", "model")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("不能为空")
        return value.strip()

    @field_validator("base_url")
    @classmethod
    def http_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("模型地址必须是 HTTP 或 HTTPS 地址")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("模型地址不能包含凭据、查询参数或片段")
        return value.rstrip("/")


class RecordSettings(SettingsModel):
    categories: dict[str, dict[str, list[str]]]
    meal_types: list[str]

    @field_validator("categories")
    @classmethod
    def validate_categories(cls, value: dict) -> dict:
        if set(value) != set(TRANSACTION_TYPES):
            raise ValueError("分类必须包含支出、收入和迁移")
        for groups in value.values():
            for name, children in groups.items():
                if not name.strip() or name != name.strip():
                    raise ValueError("分类名称不能为空或含首尾空白")
                cls.validate_labels(children)
        return value

    @field_validator("meal_types")
    @classmethod
    def validate_labels(cls, values: list[str]) -> list[str]:
        if any(not v.strip() or v != v.strip() for v in values):
            raise ValueError("标签不能为空或含首尾空白")
        if len(set(values)) != len(values):
            raise ValueError("标签不能重复")
        return values


class AccessSettings(SettingsModel):
    enabled: bool
    password_configured: bool
    cookie_secure: bool
    session_seconds: int = Field(gt=0)


class SettingsResponse(SettingsModel):
    revision: str
    model: ModelSettings
    records: RecordSettings
    access: AccessSettings
    api_key_configured: bool
    data_directory: str
    database_path: str


class ModelSettingsUpdate(SettingsModel):
    revision: str
    model: ModelSettings
    api_key: str | None = None


class RecordSettingsUpdate(SettingsModel):
    revision: str
    records: RecordSettings


class AccessSettingsUpdate(SettingsModel):
    revision: str
    enabled: bool
    password: str | None = None
    cookie_secure: bool
    session_seconds: int = Field(gt=0)
    reset_sessions: bool = False


class StoredAccess(SettingsModel):
    enabled: bool = False
    password_hash: str = ""
    cookie_secure: bool = False
    session_seconds: int = Field(default=2592000, gt=0)


class StoredSettings(SettingsModel):
    model: ModelSettings
    records: RecordSettings
    access: StoredAccess = Field(default_factory=StoredAccess)
    api_key_encrypted: str = ""
    signing_key_encrypted: str = ""
