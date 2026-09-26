"""Unit tests for Phase 17: Dashboard Web Application and Endpoints."""

import pytest
from fastapi.testclient import TestClient

from dashboard.app import app


@pytest.fixture
def client():
    return TestClient(app)


def test_dashboard_api_state(client):
    """Verify /api/state returns WorldState and agent state."""
    res = client.get("/api/state")
    assert res.status_code == 200
    data = res.json()
    assert "world_state" in data
    assert "agent_state" in data
    assert "robot" in data["world_state"]


def test_dashboard_api_map(client):
    """Verify /api/map returns nodes and corridor status."""
    res = client.get("/api/map")
    assert res.status_code == 200
    data = res.json()
    assert "nodes" in data
    assert "reception" in data["nodes"]
    assert "corridor_status" in data


def test_dashboard_api_chaos_endpoints(client):
    """Verify chaos engineering injection and reset endpoints."""
    # Inject obstacle
    res_obs = client.post("/api/chaos/inject_obstacle", json={"corridor_id": "corridor_A", "location": [5.0, 8.0]})
    assert res_obs.status_code == 200
    assert res_obs.json()["success"] is True

    # Restore corridor
    res_rest = client.post("/api/chaos/restore_corridor?corridor_id=corridor_A")
    assert res_rest.status_code == 200

    # Reset world
    res_reset = client.post("/api/reset")
    assert res_reset.status_code == 200
    assert res_reset.json()["success"] is True
