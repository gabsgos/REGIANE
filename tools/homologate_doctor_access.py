from __future__ import annotations

import json
import secrets
from datetime import UTC, datetime
from pathlib import Path

from backend.app.main import create_app
from fastapi.testclient import TestClient

SECRET_FILE = Path("data/homologation-doctor.secret")
REPORT = Path("docs/permissoes_e11_medico_homologacao.json")


def read_credentials() -> dict[str, str]:
    return dict(
        line.split("=", 1)
        for line in SECRET_FILE.read_text(encoding="utf-8").splitlines()
        if "=" in line
    )


def main() -> int:
    credentials = read_credentials()
    username = credentials["username"]
    new_password = secrets.token_urlsafe(20)
    client = TestClient(create_app())
    first_login = client.post(
        "/api/auth/login",
        json={"username": username, "password": credentials["password"]},
    )
    csrf = client.cookies.get("abel_csrf")
    password_change = client.post(
        "/api/auth/password",
        headers={"X-CSRF-Token": csrf or ""},
        json={"current_password": credentials["password"], "new_password": new_password},
    )
    verified = TestClient(create_app())
    second_login = verified.post(
        "/api/auth/login", json={"username": username, "password": new_password}
    )
    worklist = verified.get("/api/clinical/worklist")
    finance = verified.get("/api/finance/summary")
    me = verified.get("/api/auth/me")
    criteria = {
        "initial_login": first_login.status_code == 200,
        "mandatory_password_change": password_change.status_code == 204,
        "login_after_change": second_login.status_code == 200,
        "profile_is_medico": me.status_code == 200 and "medico" in me.json().get("roles", []),
        "clinical_worklist_allowed": worklist.status_code == 200,
        "finance_denied": finance.status_code == 403,
        "no_financial_fields_in_worklist": worklist.status_code == 200
        and all(
            field not in json.dumps(worklist.json())
            for field in ("total_amount", "paid_at", "payment_method")
        ),
    }
    result = {
        "generated_at": datetime.now(UTC).isoformat(),
        "username": username,
        "profile": "medico",
        "criteria": criteria,
        "worklist_items": worklist.json().get("total", 0) if worklist.status_code == 200 else None,
        "integrity": "PASS" if all(criteria.values()) else "FAIL",
    }
    if result["integrity"] == "PASS":
        SECRET_FILE.write_text(
            f"username={username}\npassword={new_password}\nchange_required=false\n",
            encoding="utf-8",
        )
    REPORT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["integrity"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
