"""Constrained MCP input/output contracts; no external API schemas are guessed."""

from typing import Annotated, Literal

from pydantic import ConfigDict, Field, field_validator

from agent.handoffs import Action, Contract, Evidence, WriteRequest

Identifier = Annotated[str, Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_.:-]+$")]
IdempotencyKey = Annotated[str, Field(min_length=8, max_length=200, pattern=r"^[A-Za-z0-9_.:-]+$")]
Query = Annotated[str, Field(max_length=4000)]


class EvidenceHit(Evidence):
    retrieval_score: float
    retrieval_variant: str


class EvidenceFilters(Contract):
    persona: str | None = Field(default=None, max_length=100)
    type: Literal["cv", "case_study", "review", "proposal", "repository"] | None = None
    project: str | None = Field(default=None, max_length=200)
    industry: str | None = Field(default=None, max_length=100)
    outcome: Literal["unknown", "won", "replied", "ignored"] | None = None


class SafeAction(Action):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True, allow_inf_nan=False)
    destination: Identifier

    @field_validator("text")
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError("Action text cannot be blank")
        return value


class DraftAction(SafeAction):
    kind: Literal["draft"]


class ProposalAction(SafeAction):
    kind: Literal["proposal"]


class MessageAction(SafeAction):
    kind: Literal["message"]


class HoldAction(Action):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True, allow_inf_nan=False)
    kind: Literal["hold"]


class EmailAction(Action):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True, allow_inf_nan=False)
    kind: Literal["email"]


class MCPWriteRequest(WriteRequest):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    idempotency_key: IdempotencyKey
    run_id: Identifier
    approval_id: Identifier | None = None


class DraftRequest(MCPWriteRequest):
    action: DraftAction


class SubmitRequest(MCPWriteRequest):
    action: ProposalAction


class MessageRequest(MCPWriteRequest):
    action: MessageAction


class HoldRequest(MCPWriteRequest):
    action: HoldAction


class EmailRequest(MCPWriteRequest):
    action: EmailAction


class CalendarSlot(Contract):
    start: str
    minutes: int = 30
    synthetic: bool = True
