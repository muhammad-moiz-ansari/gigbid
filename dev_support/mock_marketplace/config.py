from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

FaultMode = Literal["none", "outage", "rate_limit", "server_error", "timeout", "ambiguous_write"]
Operation = Literal[
    "search",
    "job",
    "client_history",
    "balance",
    "proposal",
    "messages",
    "events",
    "write",
    "reconcile",
]


class SimulatorConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    seed: int = 4016
    reply_probability: float = Field(default=0.65, ge=0, le=1)
    interview_probability: float = Field(default=0.5, ge=0, le=1)
    hire_probability: float = Field(default=0.25, ge=0, le=1)


class FaultScenario(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: FaultMode = "none"
    operations: list[Operation] = Field(default_factory=list)
    # Null means persistent; an integer consumes exactly that many matching calls.
    remaining: int | None = Field(default=None, ge=0)
    retry_after: int = Field(default=60, ge=1, le=3600)
