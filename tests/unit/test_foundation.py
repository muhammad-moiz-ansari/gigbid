import os
import subprocess
import sys

from sqlalchemy import create_engine, inspect

from apps.api.config import ROOT
from apps.api.db import Base


def test_clean_database_migration_and_repeat(tmp_path):
    # Workspace-local path avoids sandbox-specific Windows temp socket/path limits.
    target = ROOT / ".cache" / "migration-check.db"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()
    url = "sqlite:///" + target.as_posix()
    env = {**os.environ, "DATABASE_URL": url}
    for _ in range(2):
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"],
                       cwd=ROOT, env=env, check=True, capture_output=True, timeout=30)
    engine = create_engine(url)
    assert set(Base.metadata.tables) <= set(inspect(engine).get_table_names())
    engine.dispose()


def test_health_readiness_and_cookie_security(client):
    assert client.get("/health").json()["ok"] is True
    assert client.get("/ready").json()["database"] == "ready"
    result = client.post("/auth/register", json={"email": "foundation@example.test", "password": "secure-password-for-test"})
    assert result.status_code == 200
    cookie = result.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    assert result.headers["x-trace-id"]
    assert "password" not in result.json()
    assert client.get("/auth/me").json()["id"] == result.json()["id"]


def test_seed_repeat_and_profile_persistence(client, account):
    before = client.get("/evidence").json()
    assert client.post("/dev/seed").status_code == 200
    assert client.get("/evidence").json() == before
    assert all(item["synthetic"] for item in before)
    result = client.put("/auth/profile", json={"name": "Foundation check", "weekly_connects": 24})
    assert result.status_code == 200
    assert client.get("/auth/me").json()["profile"]["weekly_connects"] == 24
