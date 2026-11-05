from backend.app.api.routes import health as health_module
from backend.app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_health_check() -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "ABEL Clinica",
            "version": "1.0.0+build.61",
        "environment": "development",
        "checks": {"api": "ok", "database": "ok", "document_storage": "ok"},
    }


def test_openapi_is_available_outside_production() -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert response.json()["info"]["title"] == "ABEL Clinica"


def test_database_failure_degrades_health(monkeypatch) -> None:
    class BrokenEngine:
        def connect(self):
            raise OSError("database unavailable")

    monkeypatch.setattr(health_module, "get_engine", lambda: BrokenEngine())
    response = client.get("/api/health")
    assert response.status_code == 503
    assert response.json()["status"] == "degraded"
    assert response.json()["checks"]["database"] == "error"
