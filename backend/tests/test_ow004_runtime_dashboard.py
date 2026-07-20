from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_dashboard_contract():
    response = client.get("/runtime/dashboard")
    assert response.status_code == 200
    data = response.json()
    assert data["runtime"]["status"] in {"healthy", "degraded", "offline"}
    for key in ("cpu_percent", "memory_percent", "disk_percent"):
        assert 0 <= data["runtime"]["metrics"][key] <= 100
    assert isinstance(data["agents"], list)
    assert {"queued", "running", "completed", "failed"} <= set(data["tasks"])
