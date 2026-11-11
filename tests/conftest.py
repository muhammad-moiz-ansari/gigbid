import os
from pathlib import Path
from uuid import uuid4

import pytest

# Tests own isolated databases, inherited by MCP subprocesses.
TEST_ROOT = Path(__file__).resolve().parents[1] / ".cache/tests" / str(uuid4())
TEST_ROOT.mkdir(parents=True)
os.environ["DATABASE_URL"] = f"sqlite:///{(TEST_ROOT / 'test.db').as_posix()}"
os.environ["CHECKPOINT_URL"] = str(TEST_ROOT / "checkpoints.db")
os.environ["MCP_CALLS_PER_MINUTE"] = "10000"
os.environ["GROQ_API_KEY"] = ""  # Tests never call a hosted model; provider tests mock the HTTP transport.
os.environ["GITHUB_TOKEN"] = ""  # Repository import tests use a stand-in MCP session.

from apps.api.db import Base, engine  # noqa: E402


@pytest.fixture(autouse=True)
def database():
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from apps.api.main import app
    with TestClient(app) as client:
        yield client


@pytest.fixture
def account(client):
    result = client.post("/auth/register", json={"email": "alice@example.test", "password": "correct-horse-battery-123"})
    assert result.status_code == 200, result.text
    me = result.json()
    client.headers.update({"origin": "http://localhost:3000", "x-csrf-token": me["csrf"]})
    assert client.post("/dev/seed").status_code == 200
    return me
