from fastapi.testclient import TestClient

from apps.api.auth import service
from apps.api.config import settings
from apps.api.db import User, transaction
from apps.api.main import app


def test_password_hash_and_two_hour_session(client, monkeypatch):
    monkeypatch.setattr(service, "now", lambda: 1000)
    result = client.post("/auth/register", json={"email": "expiry@example.test", "password": "abcdef", "profile": {"name": "Test User", "persona": "own", "floor_fixed": 50, "hourly_rate": 50, "weekly_connects": 50}})
    assert result.status_code == 200
    assert "Max-Age=7200" in result.headers["set-cookie"]
    with transaction() as db:
        stored = db.get(User, result.json()["id"]).password_hash
        assert stored.startswith("$argon2id$")
        assert service.passwords.verify("abcdef", stored)
    monkeypatch.setattr(service, "now", lambda: 8199)
    assert client.get("/auth/me").status_code == 200
    monkeypatch.setattr(service, "now", lambda: 8200)
    assert client.get("/auth/me").status_code == 401


def test_csrf_and_tenant_isolation(client, account):
    run = client.post("/jobs/mock-api/analyse").json()
    with TestClient(app) as other:
        assert other.get("/runs").status_code == 401
        registered = other.post("/auth/register", json={"email": "bob@example.test", "password": "different-password-123", "profile": {"name": "Test User", "persona": "own", "floor_fixed": 50, "hourly_rate": 50, "weekly_connects": 50}}).json()
        assert registered["id"] != account["id"]
        assert other.get(f'/runs/{run["id"]}').status_code == 404
        assert other.get("/evidence").json() == []
        assert other.post("/dev/seed").status_code == 403
    client.headers["x-csrf-token"] = "wrong"
    assert client.put("/auth/profile", json={}).status_code == 403


def test_password_and_session_revocation(client, account):
    assert client.post("/auth/login", json={"email": account["email"], "password": "wrong-password-value"}).status_code == 401
    assert client.post("/auth/logout").status_code == 200
    assert client.get("/auth/me").status_code == 401


def test_local_registration_accepts_six_characters_and_checks_origin(client, monkeypatch):
    monkeypatch.setattr(settings(), "web_origin", "http://localhost:3000")
    origin = {"origin": "http://127.0.0.1:3000"}
    credentials = {"email": "local@example.test", "password": "abcdef", "profile": {"name": "Test User", "persona": "own", "floor_fixed": 50, "hourly_rate": 50, "weekly_connects": 50}}
    assert client.post("/auth/register", headers=origin,
                       json={**credentials, "password": "abcde"}).status_code == 422
    foreign = {"origin": "http://localhost:3001"}
    assert client.post("/auth/register", headers=foreign, json=credentials).status_code == 403

    registered = client.post("/auth/register", headers=origin, json=credentials)
    assert registered.status_code == 200
    csrf = {"x-csrf-token": registered.json()["csrf"]}
    assert client.get("/auth/me").status_code == 200
    assert client.post("/auth/logout", headers={**foreign, **csrf}).status_code == 403
    assert client.post("/auth/logout", headers={**origin, **csrf}).status_code == 200
    assert client.post("/auth/login", headers=origin, json=credentials).status_code == 200
