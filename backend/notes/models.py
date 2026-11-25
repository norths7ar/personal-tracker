from datetime import date as Date

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class EventDateRange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_date: Date
    end_date: Date

    @model_validator(mode="after")
    def validate_order(self):
        if self.start_date > self.end_date:
            raise ValueError("事件结束日期不能早于开始日期")
        return self


def _normalize_event_dates(items: list[EventDateRange]) -> list[EventDateRange]:
    unique = {(item.start_date, item.end_date): item for item in items}
    return [unique[key] for key in sorted(unique)]


class NoteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(default="", max_length=200)
    content: str = Field(min_length=1, max_length=100_000)
    recorded_date: Date
    event_dates: list[EventDateRange] = Field(default_factory=list, max_length=50)

    @field_validator("title", mode="before")
    @classmethod
    def strip_title(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("content")
    @classmethod
    def nonblank_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("随手记正文不能为空")
        return value

    @field_validator("event_dates")
    @classmethod
    def clean_dates(cls, value: list[EventDateRange]) -> list[EventDateRange]:
        return _normalize_event_dates(value)


class NoteUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=200)
    content: str | None = Field(default=None, min_length=1, max_length=100_000)
    recorded_date: Date | None = None
    event_dates: list[EventDateRange] | None = Field(default=None, max_length=50)

    @field_validator("title", mode="before")
    @classmethod
    def strip_title(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("content")
    @classmethod
    def nonblank_content(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("随手记正文不能为空")
        return value

    @field_validator("event_dates")
    @classmethod
    def clean_dates(cls, value: list[EventDateRange] | None) -> list[EventDateRange] | None:
        return _normalize_event_dates(value) if value is not None else None

    @model_validator(mode="after")
    def reject_nulls(self):
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("字段不能为 null")
        return self


class NoteItem(BaseModel):
    id: int
    title: str
    content: str
    recorded_date: Date
    event_dates: list[EventDateRange]
    created_at: str
    updated_at: str


class NotesListResponse(BaseModel):
    items: list[NoteItem]
    years: list[str]
