from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    database_url: str = "sqlite:///data/processed/gigbid.db"
    checkpoint_url: str = "data/processed/checkpoints.db"
    marketplace_mode: Literal["mock", "gigsim", "upwork"] = "mock"
    model_profile: Literal["open", "paid"] = "open"
    retrieval_variant: str = ""
    ollama_url: str = "http://127.0.0.1:11434"
    redis_url: str = "redis://localhost:6379/0"
    qdrant_url: str = "http://localhost:6333"
    queue_mode: Literal["database", "celery"] = "database"
    mcp_transport: Literal["stdio", "http"] = "stdio"
    portfolio_mcp_url: str = "http://localhost:8001/mcp"
    marketplace_mcp_url: str = "http://localhost:8002/mcp"
    workspace_mcp_url: str = "http://localhost:8003/mcp"
    web_origin: str = "http://localhost:3000"
    cookie_secure: bool = False
    session_hours: int = 12
    model_timeout_seconds: int = 45
    tool_timeout_seconds: int = 30
    mcp_calls_per_minute: int = 60
    max_upload_bytes: int = 2_000_000
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_base_url: str = "http://localhost:3001"


@lru_cache
def settings() -> Settings:
    return Settings()
