from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class JobSpec(Contract):
    id: str
    title: str
    description: str
    skills: list[str]
    budget: float = Field(ge=0)
    connects: int = Field(ge=0)
    client_id: str
    deliverables: list[str] = []
    screening_questions: list[str] = []
    timeline: str = "Unspecified"


class RiskReport(Contract):
    score: float = Field(ge=0, le=1)
    flags: list[str]
    reasons: list[str]


class FitReport(Contract):
    score: float = Field(ge=0, le=1)
    matrix: dict[str, list[str]]
    evidence: list[dict]


class BidDecision(Contract):
    action: Literal["skip", "watch", "bid"]
    reason: str


class PriceQuote(Contract):
    amount: float = Field(gt=0)
    connects: int = Field(ge=0)
    rationale: str


class ProposalDraft(Contract):
    text: str = Field(min_length=1, max_length=10000)
    screening_answers: dict[str, str] = {}
    version: int = Field(ge=1, default=1)
    evidence_ids: list[str] = []


class Critique(Contract):
    passed: bool
    comments: list[str]


class ComplianceVerdict(Contract):
    passed: bool
    reasons: list[str]


class Evidence(Contract):
    id: str
    tenant: str
    source: str
    location: str
    text: str
    content_hash: str
    type: str
    persona: str
    project: str
    skills: list[str]
    date: str
    industry: str
    outcome: str = "unknown"
    synthetic: bool = False


class Action(Contract):
    kind: Literal["proposal", "message", "draft", "hold", "email"]
    destination: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=10000)
    price: float = Field(ge=0, default=0)
    version: int = Field(ge=1, default=1)
    evidence_hashes: dict[str, str] = {}


class WriteRequest(Contract):
    action: Action
    idempotency_key: str = Field(min_length=8, max_length=200)
    run_id: str = Field(min_length=1)
    approval_id: str | None = None
    dry_run: bool = True


class WriteResult(Contract):
    mode: str
    dry_run: bool
    payload: dict
    connects_cost: int = 0
    effect_id: str | None = None
    status: str = "preview"
