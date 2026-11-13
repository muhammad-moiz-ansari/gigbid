from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Credentials(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=6, max_length=128)

    @field_validator("email")
    @classmethod
    def email_shape(cls, value):
        import re
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("Enter a valid email")
        return value.lower().strip()


class Profile(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    name: str = Field(default="Freelancer", min_length=1, max_length=100)
    persona: Literal["own", "full-stack", "ai-ml", "data-analyst"] = "own"
    floor_fixed: float = Field(default=50, gt=0, le=1_000_000)
    weekly_connects: int = Field(default=50, ge=0, le=10000)
    auto_skip: bool = True
    saved_query: str = Field(default="", max_length=200)
    interval_seconds: int = Field(default=14400, ge=300)
    hourly_rate: float = Field(default=50, gt=0, le=10000)
    min_budget: float = Field(default=0, ge=0, le=1_000_000)
    max_connects: int | None = Field(default=None, ge=0, le=10000)
    required_skills: list[str] = Field(default=[], max_length=100)
    marketplace_mode: Literal["mock", "gigsim", "upwork"] | None = None


class Upload(BaseModel):
    source: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=2_000_000)
    type: Literal["cv", "case_study", "review", "proposal", "repository"] = "case_study"
    skills: list[str] = Field(default=[], max_length=100)
    project: str = Field(default="Own portfolio", max_length=200)
    persona: str = Field(default="own", max_length=100)
    industry: str = Field(default="unspecified", max_length=100)
    date: str = Field(default="unspecified", max_length=30)
    outcome: Literal["unknown", "won", "replied", "ignored"] = "unknown"


class GitHubImport(BaseModel):
    repository: str = Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", max_length=200)


class ApprovalDecision(BaseModel):
    decision: Literal["approve", "reject", "edit", "regenerate"]
    text: str | None = Field(default=None, max_length=10000)
    reason: str = Field(default="", max_length=1000)
    paragraph: int = Field(default=0, ge=0, le=100)


class RunView(BaseModel):
    id: str
    subject: str
    kind: str
    status: str
    state: dict
    trace_id: str
    draft_paragraphs: list[str] = []
    approval_status: str | None = None


class RunEvent(BaseModel):
    id: int
    name: str
    payload: dict
    created: float
    trace_id: str


class EventPage(BaseModel):
    events: list[RunEvent]
    next_cursor: int
    has_more: bool


class SessionView(BaseModel):
    id: str
    email: str
    csrf: str
    profile: dict


class SkipInput(BaseModel):
    reason: str = Field(default="", max_length=500)


class ReplayInput(BaseModel):
    checkpoint_id: str = Field(min_length=1, max_length=100)


class CategoryStats(BaseModel):
    category: str
    submitted: int
    replied: int
    hired: int
    connects_spent: int
    reply_rate: float | None
    hire_rate: float | None


class Spread(BaseModel):
    p50: float | None
    p95: float | None


class ReasonCount(BaseModel):
    reason: str
    count: int


class Analytics(BaseModel):
    mode: str
    synthetic: bool
    submitted: int
    replied: int
    hired: int
    reply_rate: float | None
    hire_rate: float | None
    connects: dict
    by_category: list[CategoryStats]
    proposal_tokens: Spread
    proposal_active_seconds: Spread
    proposal_api_usd: Spread
    rejection_reasons: list[ReasonCount]
    runs: int
    usage: list[dict]
    official_outcomes: str


class MessageInput(BaseModel):
    conversation: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=10000)


class FaultInput(BaseModel):
    mode: Literal["none", "outage", "rate_limit", "timeout", "ambiguous_write"]
