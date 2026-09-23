from fastapi.testclient import TestClient

from app import config
from app.main import app


def test_endpoints_in_demo_mode():
    with TestClient(app) as c:
        h = c.get("/api/health").json()
        assert h["ok"] and h["mode"] == "demo"
        meta = c.get("/api/meta").json()
        assert len(meta["demo_prompts"]) >= 3
        r = c.post("/api/ask", json={"message": "Проверь операцию T-DEMO-1", "client_id": "C-DEMO-1"})
        assert r.status_code == 200
        body = r.json()
        assert body["answer"]["answer"] and body["meta"]["mode"] == "demo"
        assert c.get("/").status_code == 200
        assert "<html" in c.get("/").text.lower()
        assert c.get("/api/clients").json()[0]["client_id"]


def test_validation_and_rate_limit(monkeypatch):
    monkeypatch.setattr(config, "RATE_LIMIT_PER_MIN", 2)
    with TestClient(app) as c:
        assert c.post("/api/ask", json={"message": ""}).status_code == 422
        codes = [c.post("/api/ask", json={"message": "тест"}, headers={"x-forwarded-for": "9.9.9.9"}).status_code
                 for _ in range(3)]
        assert codes == [200, 200, 429]
