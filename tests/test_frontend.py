from pathlib import Path

from backend.app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_modular_frontend_is_served() -> None:
    response = client.get("/abel.html")
    script = client.get("/abel/assets/js/app.js")
    assert response.status_code == 200
    assert script.status_code == 200
    assert 'type="module"' in response.text
    assert "/api/auth/login" not in response.text
    assert 'api("/auth/login"' in script.text
    assert client.get("/abel/api/health").status_code == 200


def test_frontend_has_no_unsafe_html_or_mock_login() -> None:
    contents = "\n".join(
        path.read_text(encoding="utf-8")
        for path in Path("frontend").rglob("*")
        if path.suffix in {".html", ".css", ".js"}
    )
    assert "innerHTML" not in contents
    assert "perfil-simulado" not in contents
    assert "123456" not in contents
    assert "localStorage" not in contents


def test_frontend_exposes_financial_reports_and_user_search() -> None:
    html = Path("frontend/index.html").read_text(encoding="utf-8")
    script = Path("frontend/js/app.js").read_text(encoding="utf-8")
    for element_id in (
        "finance-report-form",
        "finance-user",
        "finance-movements-body",
        "patient-finance-search-form",
        "patient-monthly-body",
        "user-search-form",
        "new-cpf",
        "new-birth-date",
        "new-phone",
        "new-email",
        "new-address",
        "new-professional-id",
        "edit-active",
        "user-submit",
        "user-cancel-edit",
        "clinical-worklist-body",
        "delivery-queue-body",
        "delivery-queue-refresh",
    ):
        assert f'id="{element_id}"' in html
    assert 'api(`/finance/report?' in script
    assert 'api(`/finance/patients/${patientId}/report`)' in script
    assert 'method: "PUT"' in script
    assert "resetUserPassword" in script
    assert 'api("/clinical/worklist")' in script
    assert 'api("/documents/delivery/queue")' in script
    assert "WhatsApp manual" in script
