import asyncio
import os
import socket
import subprocess
import sys

import httpx
import pytest

from agent.mcp_client import ToolFailure, gateway
from apps.api.config import settings


def available_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.mark.asyncio
async def test_real_http_server_outage_preserves_work_and_recovers(
    mcp_identity, client, monkeypatch
):
    ports = [available_port() for _ in range(3)]
    for name, port in zip(("marketplace", "portfolio", "workspace"), ports, strict=True):
        monkeypatch.setattr(settings(), f"{name}_mcp_url", f"http://127.0.0.1:{port}/mcp")
    monkeypatch.setattr(settings(), "mcp_transport", "http")
    monkeypatch.setattr(settings(), "mcp_retry_max_delay_seconds", 0)
    env = {
        **os.environ,
        "MCP_TRANSPORT": "http",
        "MARKETPLACE_MCP_URL": settings().marketplace_mcp_url,
    }

    def start():
        return subprocess.Popen(
            [sys.executable, "-m", "mcp_servers.marketplace.server"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )

    async def ready(process):
        async with httpx.AsyncClient(timeout=0.5) as probe:
            for _ in range(100):
                if process.poll() is not None:
                    raise AssertionError("Local MCP process exited during startup")
                try:
                    response = await probe.post(settings().marketplace_mcp_url, json={})
                    if response.status_code == 401:
                        return
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(0.05)
        raise AssertionError("Local MCP server did not become ready")

    process = start()
    try:
        await ready(process)
        run = client.post("/jobs/mock-api/analyse").json()  # Queue only; no worker/model started.
        async with gateway(mcp_identity[1], "http-recovery-test") as tools:
            assert tools.availability()["marketplace"]["available"]
            assert not tools.availability()["portfolio"]["available"]
            assert (await tools.call("intake", "get_job", {"job_id": "mock-api"}))[
                "id"
            ] == "mock-api"
            process.terminate()
            process.wait(timeout=10)
            with pytest.raises(ToolFailure):
                await tools.call("intake", "get_job", {"job_id": "mock-api"})
            assert not tools.availability()["marketplace"]["available"]
            status = client.get("/status").json()
            assert (
                not status["marketplace_available"] and "queued work is retained" in status["error"]
            )
            assert client.get(f"/runs/{run['id']}").json()["status"] == "queued"
            process = start()
            await ready(process)
            assert (await tools.call("intake", "get_job", {"job_id": "mock-api"}))[
                "id"
            ] == "mock-api"
            assert client.get("/status").json()["marketplace_available"]
    finally:
        process.terminate()
        process.wait(timeout=10)
