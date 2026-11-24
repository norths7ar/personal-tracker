from datetime import date as Date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

JobStatus = Literal["待看", "已沟通", "已投递", "面试中", "已放弃"]
MatchLevel = Literal["高", "中高", "中", "中低", "低"]
AnalysisStatus = Literal["none", "pending", "complete", "failed"]
MatchSource = Literal["none", "text", "fields"]
AnalysisDecision = Literal["merge_reuse", "merge_analyze", "new_analyze"]

MAX_JD_LENGTH = 60_000
MAX_RESUME_LENGTH = 120_000


class JobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ProfileWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resume_text: str = Field(max_length=MAX_RESUME_LENGTH)
    supplemental_notes: str = Field(max_length=30_000)
    imported_filename: str | None = Field(default=None, max_length=255)


class Profile(BaseModel):
    resume_text: str
    supplemental_notes: str
    imported_filename: str | None
    imported_at: str | None
    updated_at: str | None


class DocxPreview(BaseModel):
    resume_text: str
    source_filename: str


class JobFields(JobRequest):
    company: str = Field(default="", max_length=250)
    role: str = Field(min_length=1, max_length=250)
    city: str = Field(default="", max_length=250)
    salary: str = Field(default="", max_length=250)
    status: JobStatus = "待看"
    notes: str = Field(default="", max_length=30_000)
    is_headhunter: bool = False
    headhunter_agency: str = Field(default="", max_length=250)


class JobUpdate(JobRequest):
    company: str | None = Field(default=None, max_length=250)
    role: str | None = Field(default=None, min_length=1, max_length=250)
    city: str | None = Field(default=None, max_length=250)
    salary: str | None = Field(default=None, max_length=250)
    status: JobStatus | None = None
    notes: str | None = Field(default=None, max_length=30_000)
    is_headhunter: bool | None = None
    headhunter_agency: str | None = Field(default=None, max_length=250)

    @model_validator(mode="after")
    def non_null_fields(self):
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("字段不能为 null，清空文本请传空字符串")
        return self


class EncounterInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: Date
    platform: str = Field(min_length=1, max_length=150)
    contact: str = Field(default="", max_length=250)
    salary: str = Field(default="", max_length=250)
    raw_jd: str = Field(min_length=1, max_length=MAX_JD_LENGTH)
    notes: str = Field(default="", max_length=30_000)

    @field_validator("platform", "contact", "salary", "notes", mode="before")
    @classmethod
    def trim_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("raw_jd")
    @classmethod
    def jd_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("JD 原文不能为空")
        return value


class Encounter(EncounterInput):
    id: int


class Analysis(BaseModel):
    id: int
    match_level: MatchLevel
    verdict: str
    analysis_markdown: str
    greeting: str | None
    created_at: str


class Message(BaseModel):
    id: int
    role: Literal["user", "assistant"]
    content: str
    created_at: str


class UnfinishedQuestion(BaseModel):
    request_id: UUID
    question: str
    status: Literal["pending", "failed"]
    error: str


class JobSummary(JobFields):
    id: int
    encounter_count: int
    latest_encounter_date: Date
    latest_analysis: Analysis | None
    analysis_status: AnalysisStatus
    analysis_error: str
    analysis_stale: bool


class JobDetail(JobSummary):
    encounters: list[Encounter]
    analyses: list[Analysis]
    messages: list[Message]
    unfinished_questions: list[UnfinishedQuestion]


class IntakeCreate(EncounterInput):
    request_id: UUID
    greeting_enabled: bool | None = None


class Intake(BaseModel):
    id: int
    encounter: EncounterInput
    greeting_enabled: bool
    fields: JobFields | None
    candidates: list[JobSummary]
    match_source: MatchSource
    status: Literal["pending", "ready", "failed", "saved"]
    error: str
    job_id: int | None


class IntakeSave(JobRequest):
    decision: AnalysisDecision
    job_id: int | None = Field(default=None, gt=0)
    fields: JobFields | None = None
    encounter: EncounterInput | None = None


class AnalysisRequest(JobRequest):
    request_id: UUID


class QuestionRequest(AnalysisRequest):
    question: str = Field(min_length=1, max_length=10_000)


class Context(BaseModel):
    text: str
