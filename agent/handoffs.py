from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from agent.model import config


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, hide_input_in_errors=True)


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
    hidden_needs: list[str] = []


class RiskReport(Contract):
    score: float = Field(ge=0, le=1)
    flags: list[str]
    reasons: list[str]

    @field_validator("flags")
    @classmethod
    def configured(cls, flags):
        """Flags come from the policy list in config.yaml, so a policy update needs no code change."""
        unknown = sorted(set(flags) - set(config()["policy"]["risk_flags"]))
        if unknown:
            raise ValueError(f"Unknown risk flags: {unknown}")
        return flags


class FitReport(Contract):
    score: float = Field(ge=0, le=1)
    matrix: dict[str, list[str]]
    evidence: list["RetrievedEvidence"]


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


class ScreeningAnswer(Contract):
    answer: str = Field(min_length=1, max_length=4000)


class IntentReport(Contract):
    intent: Literal["question", "negotiation", "interview", "scam"]
    reasons: list[str]


class Critique(Contract):
    passed: bool
    comments: list[str]


class ComplianceVerdict(Contract):
    passed: bool
    reasons: list[str]


class NodeUsage(Contract):
    node: str
    model: str
    provider: str = "unspecified"
    tokens: int = Field(ge=0)
    api_usd: float | None = Field(default=None, ge=0)
    latency_seconds: float = Field(default=0, ge=0)
    generated_tokens: int = Field(default=0, ge=0)
    generation_seconds: float = Field(default=0, ge=0)
    test_double: bool = False
    usage_complete: bool = True
    attempts: int = Field(default=1, ge=1)
    prompt_version: str = "unspecified"


class AnalystHandoff(Contract):
    role: Literal["analyst"] = "analyst"
    result: JobSpec


class RiskHandoff(Contract):
    role: Literal["risk"] = "risk"
    result: RiskReport


class FitHandoff(Contract):
    role: Literal["matcher"] = "matcher"
    result: FitReport


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


class RetrievedEvidence(Evidence):
    retrieval_score: float | None = None
    retrieval_variant: str | None = None


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
    terms: dict = {}  # marketplace terms sent with the action, shown in the preview (Upwork: duration, payment)
