from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    database_url: str = "sqlite:///data/processed/gigbid.db"
    checkpoint_url: str = "data/processed/checkpoints.db"
    marketplace_mode: Literal["mock", "gigsim", "upwork"] = "mock"
    model_profile: Literal["open", "open_local", "paid"] = "open"
    groq_api_key: str = ""
    github_token: str = ""
    token_encryption_key: str = ""
    upwork_redirect_uri: str = "http://localhost:3000/api/integrations/upwork/callback"
    retrieval_variant: str = ""
    ollama_url: str = "http://127.0.0.1:11434"
    redis_url: str = "redis://localhost:6379/0"
    qdrant_url: str = "http://localhost:6333"
    qdrant_mode: Literal["local", "server"] = "local"
    qdrant_path: str = "data/processed/qdrant"
    queue_mode: Literal["database", "celery"] = "database"
    mcp_transport: Literal["stdio", "http"] = "stdio"
    mcp_bind_host: str = "127.0.0.1"
    mcp_allowed_hosts: list[str] = ["127.0.0.1:*", "localhost:*", "[::1]:*"]
    mcp_server_timeout_seconds: float = Field(default=20, gt=0, le=180)
    mcp_retry_max_delay_seconds: float = Field(default=2, ge=0, le=10)
    portfolio_mcp_url: str = "http://localhost:8001/mcp"
    marketplace_mcp_url: str = "http://localhost:8002/mcp"
    workspace_mcp_url: str = "http://localhost:8003/mcp"
    web_origin: str = "http://localhost:3000"
    cookie_secure: bool = False
    session_hours: int = 12
    model_timeout_seconds: int = 120
    tool_timeout_seconds: int = 30
    mcp_calls_per_minute: int = Field(default=60, ge=1)
    max_upload_bytes: int = 2_000_000
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_base_url: str = "http://localhost:3001"


@lru_cache
def settings() -> Settings:
    return Settings()
