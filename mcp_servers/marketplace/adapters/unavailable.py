"""Explicit port boundary for integrations whose contracts have not been supplied."""

from agent.handoffs import JobSpec, WriteRequest, WriteResult
from agent.marketplace_port import (
    AdapterReadiness,
    Capabilities,
    ClientHistory,
    ConnectsBalance,
    MarketplaceEvent,
    MarketplaceMessage,
    MarketplaceProposal,
    Unavailable,
)


class UnavailableMarketplace:
    capabilities = Capabilities()
    readiness: AdapterReadiness

    def search(self, tenant: str, query: str = "") -> list[JobSpec]:
        raise Unavailable(self.readiness.detail)

    def job(self, tenant: str, job_id: str) -> JobSpec:
        raise Unavailable(self.readiness.detail)

    def client_history(self, tenant: str, client_id: str) -> ClientHistory:
        raise Unavailable(self.readiness.detail)

    def balance(self, tenant: str) -> ConnectsBalance:
        raise Unavailable(self.readiness.detail)

    def proposal(self, tenant: str, proposal_id: str) -> MarketplaceProposal:
        raise Unavailable(self.readiness.detail)

    def messages(self, tenant: str, conversation: str) -> list[MarketplaceMessage]:
        raise Unavailable(self.readiness.detail)

    def events(self, tenant: str, after: int = 0) -> list[MarketplaceEvent]:
        raise Unavailable(self.readiness.detail)

    def write(self, tenant: str, request: WriteRequest) -> WriteResult:
        raise Unavailable(self.readiness.detail)

    def reconcile(self, tenant: str, key: str) -> WriteResult | None:
        raise Unavailable(self.readiness.detail)
