from typing import Literal

from pydantic import BaseModel, Field, field_validator


class Credentials(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=12, max_length=128)

    @field_validator("email")
    @classmethod
    def email_shape(cls, value):
        import re
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("Enter a valid email")
        return value.lower().strip()


class Profile(BaseModel):
    name: str = Field(default="Freelancer", min_length=1, max_length=100)
    persona: Literal["own", "full-stack", "ai-ml", "data-analyst"] = "own"
    floor_fixed: float = Field(default=50, gt=0, le=1_000_000)
    weekly_connects: int = Field(default=50, ge=0, le=10000)
    auto_skip: bool = True
    saved_query: str = Field(default="", max_length=200)
    interval_seconds: int = Field(default=14400, ge=300)


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


class SessionView(BaseModel):
    id: str
    email: str
    csrf: str
    profile: dict


class MessageInput(BaseModel):
    conversation: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=10000)


class FaultInput(BaseModel):
    mode: Literal["none", "outage", "rate_limit", "timeout", "ambiguous_write"]
