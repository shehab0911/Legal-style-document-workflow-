from fastapi.testclient import TestClient

from app.main import app


def test_ready():
    with TestClient(app) as c:
        r = c.get("/ready")
        assert r.status_code == 200
        body = r.json()
        assert body.get("ready") is True
        assert body.get("database") == "ok"
