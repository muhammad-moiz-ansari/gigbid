import json
import os
import subprocess
import sys

import pytest


@pytest.mark.parametrize("mode", ["mock", "gigsim", "upwork"])
def test_status_command_reports_readiness_without_connecting(mode):
    result = subprocess.run(
        [sys.executable, "-m", "dev_support.mock_marketplace", "status"],
        env={**os.environ, "MARKETPLACE_MODE": mode},
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    data = json.loads(result.stdout)
    assert data["readiness"]["mode"] == mode
    assert data["readiness"]["implemented"] is (mode == "mock")
    assert data["readiness"]["externally_verified"] is False


def test_local_controls_refuse_official_modes():
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "dev_support.mock_marketplace",
            "advance",
            "--tenant",
            "test",
            "--tick-key",
            "test-tick-key",
        ],
        env={**os.environ, "MARKETPLACE_MODE": "gigsim"},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode != 0
    assert "only available with MARKETPLACE_MODE=mock" in result.stderr
