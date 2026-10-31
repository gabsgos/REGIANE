from backend.app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_health_check() -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "ABEL Clinica",
        "version": "0.2.3",
        "environment": "development",
    }


def test_openapi_is_available_outside_production() -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert response.json()["info"]["title"] == "ABEL Clinica"
