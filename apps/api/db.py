import hashlib
import json
from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import JSON, Boolean, Float, Integer, String, UniqueConstraint, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from apps.api.config import ROOT, settings


def uid() -> str:
    return str(uuid4())


def now() -> float:
    return datetime.now(timezone.utc).timestamp()


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    email: Mapped[str] = mapped_column(String, unique=True)
    password_hash: Mapped[str] = mapped_column(String)
    profile: Mapped[dict] = mapped_column(JSON, default=dict)


class Session(Base):
    __tablename__ = "sessions"
    token_hash: Mapped[str] = mapped_column(String, primary_key=True)
    tenant: Mapped[str] = mapped_column(String, index=True)
    csrf: Mapped[str] = mapped_column(String)
    expires: Mapped[float] = mapped_column(Float)


class Record(Base):
    """Tenant-scoped domain documents; unique natural keys include tenant and kind."""
    __tablename__ = "records"
    __table_args__ = (UniqueConstraint("tenant", "kind", "key"),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    tenant: Mapped[str] = mapped_column(String, index=True)
    kind: Mapped[str] = mapped_column(String, index=True)
    key: Mapped[str] = mapped_column(String)
    value: Mapped[dict] = mapped_column(JSON)
    created: Mapped[float] = mapped_column(Float, default=now)


class Run(Base):
    __tablename__ = "runs"
    __table_args__ = (UniqueConstraint("tenant", "kind", "subject", "generation"),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    tenant: Mapped[str] = mapped_column(String, index=True)
    kind: Mapped[str] = mapped_column(String, default="bid")
    subject: Mapped[str] = mapped_column(String)
    generation: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String, default="queued")
    state: Mapped[dict] = mapped_column(JSON, default=dict)
    lease_until: Mapped[float] = mapped_column(Float, default=0)
    resume: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    trace_id: Mapped[str] = mapped_column(String, default=uid)
    created: Mapped[float] = mapped_column(Float, default=now)


class Event(Base):
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant: Mapped[str] = mapped_column(String, index=True)
    run_id: Mapped[str] = mapped_column(String, index=True)
    name: Mapped[str] = mapped_column(String)
    payload: Mapped[dict] = mapped_column(JSON)
    trace_id: Mapped[str] = mapped_column(String)
    created: Mapped[float] = mapped_column(Float, default=now)


class Approval(Base):
    __tablename__ = "approvals"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    tenant: Mapped[str] = mapped_column(String, index=True)
    run_id: Mapped[str] = mapped_column(String, index=True)
    binding: Mapped[str] = mapped_column(String)
    payload: Mapped[dict] = mapped_column(JSON)
    decision: Mapped[str] = mapped_column(String, default="pending")
    reason: Mapped[str] = mapped_column(String, default="")
    consumed: Mapped[bool] = mapped_column(Boolean, default=False)


def engine_for(url: str):
    (ROOT / "data/processed").mkdir(parents=True, exist_ok=True)
    return create_engine(url, connect_args={"check_same_thread": False, "timeout": 30}
                         if url.startswith("sqlite") else {}, pool_pre_ping=True)


engine = engine_for(settings().database_url)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


@contextmanager
def transaction():
    with SessionLocal.begin() as db:
        yield db


def get_record(db, tenant: str, kind: str, key: str):
    from sqlalchemy import select
    return db.scalar(select(Record).where(Record.tenant == tenant, Record.kind == kind,
                                          Record.key == key))


def put_record(db, tenant: str, kind: str, key: str, value: dict):
    record = get_record(db, tenant, kind, key)
    if record:
        record.value = value
    else:
        record = Record(tenant=tenant, kind=kind, key=key, value=value)
        db.add(record)
    return record
