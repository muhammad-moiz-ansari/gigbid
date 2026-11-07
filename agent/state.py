import operator
from typing import Annotated, TypedDict


class BidState(TypedDict, total=False):
    tenant: str
    run_id: str
    job: dict
    profile: dict
    analyses: Annotated[list[dict], operator.add]
    job_spec: dict
    risk: dict
    fit: dict
    decision: dict
    price: dict
    draft: dict
    verification: dict
    critique: dict
    compliance: dict
    revision: int
    preview: dict
    approval_id: str
    outcome: dict
    status: str
    usage: Annotated[list[dict], operator.add]
    steps: Annotated[int, operator.add]
    active_seconds: Annotated[float, operator.add]
    edit: dict
    conversation: str
    intent: str
    messages: list[dict]
    memory: list[dict]
