from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

from typing_extensions import NotRequired, TypedDict

from agent.handoffs import JobSpec, WriteRequest, WriteResult


@dataclass(frozen=True)
class Capabilities:
    search: bool = False
    drafts: bool = False
    submit: bool = False
    messages: bool = False
    reconciliation: bool = False
    client_history: bool = False
    connects: bool = False
    proposals: bool = False
    events: bool = False


@dataclass(frozen=True)
class AdapterReadiness:
    mode: Literal["mock", "gigsim", "upwork"]
    implemented: bool
    contract_verified: bool
    externally_verified: bool
    synthetic: bool
    detail: str


class ClientHistory(TypedDict):
    id: str
    verified: bool
    spend: float
    hires: int
    synthetic: bool


class ConnectsBalance(TypedDict):
    balance: int
    spent: int
    weekly_spent: int
    weekly_limit: int
    week: str


class MarketplaceMessage(TypedDict):
    id: str
    conversation: str
    text: str
    direction: Literal["inbound", "outbound"]
    synthetic: bool


PipelineStatus = Literal["drafted", "submitted", "viewed", "replied", "interview", "hired", "lost"]


class MarketplaceEvent(TypedDict):
    id: str
    sequence: int
    subject: str
    proposal_id: str | None
    status: PipelineStatus | Literal["sent", "received"]
    synthetic: bool
    kind: Literal["proposal", "message"]
    message_id: NotRequired[str]


class MarketplaceProposal(TypedDict):
    id: str
    destination: str
    text: str
    price: float
    version: int
    status: PipelineStatus
    run_id: str
    synthetic: bool


class Unavailable(RuntimeError):
    pass


class RateLimited(Unavailable):
    status_code = 429

    def __init__(self, retry_after: int = 60):
        self.retry_after = retry_after
        super().__init__(f"Synthetic marketplace rate_limit; retry after {retry_after} seconds")


class MarketplaceServerError(Unavailable):
    status_code = 503


class MarketplaceTimeout(Unavailable):
    pass


class AmbiguousWrite(Unavailable):
    def __init__(self, key: str):
        self.idempotency_key = key
        super().__init__(
            "Synthetic response lost after write; reconcile the stable idempotency key"
        )


class NotFound(ValueError):
    pass


class IdempotencyConflict(ValueError):
    pass


@runtime_checkable
class MarketplacePort(Protocol):
    capabilities: Capabilities
    readiness: AdapterReadiness

    def search(self, tenant: str, query: str = "") -> list[JobSpec]: ...
    def job(self, tenant: str, job_id: str) -> JobSpec: ...
    def client_history(self, tenant: str, client_id: str) -> ClientHistory: ...
    def balance(self, tenant: str) -> ConnectsBalance: ...
    def proposal(self, tenant: str, proposal_id: str) -> MarketplaceProposal: ...
    def messages(self, tenant: str, conversation: str) -> list[MarketplaceMessage]: ...
    def events(self, tenant: str, after: int = 0) -> list[MarketplaceEvent]: ...
    def write(self, tenant: str, request: WriteRequest) -> WriteResult: ...
    def reconcile(self, tenant: str, key: str) -> WriteResult | None: ...
