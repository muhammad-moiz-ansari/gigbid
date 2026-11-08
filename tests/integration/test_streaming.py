"""Real local HTTP/SSE tests; isolated database and revocable sessions."""
import json
import os
import socket
import subprocess
import sys
import time

import httpx
import pytest

from apps.api.auth.service import issue_session, token_hash
from apps.api.db import Event, Run, Session, transaction


@pytest.fixture
def live_api():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    process = subprocess.Popen([sys.executable, "-m", "uvicorn", "apps.api.main:app",
        "--host", "127.0.0.1", "--port", str(port), "--log-level", "error"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    url = f"http://127.0.0.1:{port}"
    try:
        with httpx.Client(base_url=url, timeout=5) as client:
            for _ in range(100):
                if process.poll() is not None:
                    pytest.fail("Isolated API server exited before readiness")
                try:
                    if client.get("/health").status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                time.sleep(.1)
            else:
                pytest.fail("Isolated API server did not become ready")
            yield client
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def frame(lines):
    values = {}
    for line in lines:
        if not line:
            if values:
                return values
            continue
        if line.startswith(":"):
            continue
        key, _, value = line.partition(":")
        values[key] = value.strip()
    raise AssertionError("Stream closed before the expected frame")


def add_event(tenant, run_id, name):
    with transaction() as db:
        row = Event(tenant=tenant, run_id=run_id, name=name,
                    payload={"message": "Contact private@example.test", "tokens": 22}, trace_id="trace-test")
        db.add(row)
        db.flush()
        return row.id


def setup(client, account):
    run_id = client.post("/jobs/mock-api/analyse").json()["id"]
    with transaction() as db:
        token, _ = issue_session(db, account["id"])
    return run_id, token


def test_history_is_paginated_tenant_scoped_and_redacted(client, account):
    run_id, _ = setup(client, account)
    ids = [add_event(account["id"], run_id, f"real:{n}") for n in range(4)]
    first = client.get(f"/runs/{run_id}/history", params={"limit": 2}).json()
    assert [item["id"] for item in first["events"]] == ids[:2]
    assert first["has_more"] and first["next_cursor"] == ids[1]
    assert "private@" not in str(first) and first["events"][0]["payload"]["tokens"] == 22
    second = client.get(f"/runs/{run_id}/history", params={"after": first["next_cursor"], "limit": 2}).json()
    assert [item["id"] for item in second["events"]] == ids[2:]
    assert not second["has_more"]
    assert client.get(f"/runs/{run_id}/history?after=-1").status_code == 422
    assert client.get(f"/runs/{run_id}/history?limit=501").status_code == 422
    with transaction() as db:
        foreign = Run(tenant="another-tenant", subject="foreign", state={})
        db.add(foreign)
        db.flush()
        foreign_id = foreign.id
    assert client.get(f"/runs/{foreign_id}/history").status_code == 404
    assert client.get(f"/runs/{foreign_id}/events").status_code == 404


def test_sse_replays_cursor_then_streams_new_rows_and_revokes_session(client, account, live_api):
    run_id, token = setup(client, account)
    first = add_event(account["id"], run_id, "real:first")
    second = add_event(account["id"], run_id, "real:second")
    headers = {"authorization": f"Bearer {token}", "last-event-id": str(first)}
    with live_api.stream("GET", f"/runs/{run_id}/events", headers=headers) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert response.headers["x-accel-buffering"] == "no"
        lines = response.iter_lines()
        assert frame(lines)["retry"] == "1500"
        replay = frame(lines)
        assert int(replay["id"]) == second
        assert json.loads(replay["data"])["name"] == "real:second"
        third = add_event(account["id"], run_id, "real:third")
        assert int(frame(lines)["id"]) == third
        with transaction() as db:
            db.delete(db.get(Session, token_hash(token)))
        assert frame(lines)["event"] == "session-expired"
    assert live_api.get(f"/runs/{run_id}/events", headers=headers).status_code == 401
    assert live_api.get(f"/runs/{run_id}/history").status_code == 401


def test_sse_reconnect_does_not_repeat_seen_rows(client, account, live_api):
    run_id, token = setup(client, account)
    old = add_event(account["id"], run_id, "real:seen")
    new = add_event(account["id"], run_id, "real:missed-during-disconnect")
    headers = {"authorization": f"Bearer {token}", "last-event-id": str(old)}
    with live_api.stream("GET", f"/runs/{run_id}/events?after=0", headers=headers) as response:
        lines = response.iter_lines()
        frame(lines)
        assert int(frame(lines)["id"]) == new
    headers["last-event-id"] = "invalid"
    assert live_api.get(f"/runs/{run_id}/events", headers=headers).status_code == 422

