from fastapi.testclient import TestClient

from apps.api.main import app


def test_csrf_and_tenant_isolation(client, account):
    run = client.post("/jobs/mock-api/analyse").json()
    with TestClient(app) as other:
        assert other.get("/runs").status_code == 401
        registered = other.post("/auth/register", json={"email": "bob@example.test", "password": "different-password-123"}).json()
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
