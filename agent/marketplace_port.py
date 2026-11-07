from dataclasses import dataclass
from typing import Protocol

from agent.handoffs import JobSpec, WriteRequest, WriteResult


@dataclass(frozen=True)
class Capabilities:
    search: bool = False
    drafts: bool = False
    submit: bool = False
    messages: bool = False
    reconciliation: bool = False


class Unavailable(RuntimeError):
    pass


class MarketplacePort(Protocol):
    capabilities: Capabilities

    def search(self, tenant: str, query: str = "") -> list[JobSpec]: ...
    def job(self, tenant: str, job_id: str) -> JobSpec: ...
    def client_history(self, tenant: str, client_id: str) -> dict: ...
    def balance(self, tenant: str) -> dict: ...
    def messages(self, tenant: str, conversation: str) -> list[dict]: ...
    def events(self, tenant: str, after: int = 0) -> list[dict]: ...
    def write(self, tenant: str, request: WriteRequest) -> WriteResult: ...
    def reconcile(self, tenant: str, key: str) -> WriteResult | None: ...
