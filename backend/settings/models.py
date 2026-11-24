"""Validated application settings; secrets never appear in public responses."""

from string import Template
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from backend.constants import TRANSACTION_TYPES


class SettingsModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


PROMPT_PLACEHOLDERS = {
    "expense_classifier": ("categories",),
    "diet_extractor": ("meal_time", "meal_types"),
    "batch_blocks": ("default_date", "meal_types"),
    "batch_finance_events": ("default_date", "category_context", "categories"),
    "job_extractor": ("jd", "platform"),
    "job_matcher": ("profile", "jd", "role_context", "greeting_instruction"),
}


def validate_prompt(value: str | None, name: str) -> str | None:
    if value is None:
        return None
    template = Template(value)
    if not value.strip() or not template.is_valid():
        raise ValueError("提示词不能为空，且须使用有效的 string.Template 占位符")
    required = set(PROMPT_PLACEHOLDERS[name])
    identifiers = set(template.get_identifiers())
    if identifiers != required:
        missing = required - identifiers
        unknown = identifiers - required
        detail = []
        if missing:
            detail.append("缺少占位符：" + "、".join(sorted(missing)))
        if unknown:
            detail.append("未知占位符：" + "、".join(sorted(unknown)))
        raise ValueError("；".join(detail))
    template.substitute(dict.fromkeys(required, ""))
    return value


class PromptSettings(SettingsModel):
    expense_classifier: str | None
    diet_extractor: str | None
    batch_blocks: str | None
    batch_finance_events: str | None
    job_extractor: str | None = None
    job_matcher: str | None = None

    @field_validator("*")
    @classmethod
    def valid_template(cls, value: str | None, info: ValidationInfo) -> str | None:
        return validate_prompt(value, info.field_name)


class PromptOverrides(SettingsModel):
    expense_classifier: str | None = None
    diet_extractor: str | None = None
    batch_blocks: str | None = None
    batch_finance_events: str | None = None
    job_extractor: str | None = None
    job_matcher: str | None = None

    @field_validator("*")
    @classmethod
    def valid_template(cls, value: str | None, info: ValidationInfo) -> str | None:
        return validate_prompt(value, info.field_name)


class PromptValue(SettingsModel):
    text: str
    customized: bool
    required_placeholders: list[str]


class PromptValues(SettingsModel):
    expense_classifier: PromptValue
    diet_extractor: PromptValue
    batch_blocks: PromptValue
    batch_finance_events: PromptValue
    job_extractor: PromptValue
    job_matcher: PromptValue


class PromptSettingsUpdate(SettingsModel):
    revision: str
    prompts: PromptOverrides


class ModelSettings(SettingsModel):
    protocol: Literal["openai_chat_completions"]
    thinking: Literal["default", "disabled", "enabled"]
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
    prompts: PromptValues
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
    prompts: PromptSettings
    access: StoredAccess = Field(default_factory=StoredAccess)
    api_key_encrypted: str = ""
    signing_key_encrypted: str = ""


DEFAULT_SETTINGS = {
    "model": {
        "protocol": "openai_chat_completions",
        "thinking": "disabled",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-flash",
        "temperature": 0.3,
        "max_tokens": 8000,
        "timeout": 60,
        "confidence_threshold": 0.75,
    },
    "records": {
        "categories": {
            "支出": {
                "餐饮": ["蔬果粮油", "零食饮料", "堂食", "外卖"],
                "交通": ["停车费", "加油充电", "保养修车", "火车飞机", "打车租车", "公交地铁"],
                "购物": ["日常家居", "生活家电", "数码电子", "个护美妆", "服饰运动", "其他"],
                "医疗": ["药店买药", "医院"],
                "住房": ["维修清洁", "水电燃气", "租房物业"],
                "通讯": ["话费", "订阅服务", "平台会员"],
                "旅行": ["景点门票", "美食特产", "酒店住宿", "旅行交通"],
                "娱乐": ["棋牌桌游", "足浴按摩", "运动健身", "电子游戏"],
                "红包": ["亲友红包", "工作红包"],
                "保险": [],
                "教育": [],
                "其他": ["其他"],
            },
            "收入": {"薪资": [], "退款": [], "报销": [], "其他": []},
            "迁移": {"还款": [], "投资": [], "充值提现": [], "押金": [], "其他": []},
        },
        "meal_types": ["早餐", "早午餐", "午餐", "晚餐", "夜宵", "零食"],
    },
    "prompts": {
        "expense_classifier": None,
        "diet_extractor": None,
        "batch_blocks": None,
        "batch_finance_events": None,
        "job_extractor": None,
        "job_matcher": None,
    },
}
