from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from backend.app.core.config import get_settings
from backend.app.db.models import AuditLog
from backend.app.main import app
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

SECRET_FILES = (Path("data/admin-production.secret"), Path("data/initial-admin.secret"))
OUTPUT = Path("docs/fase_6_validacao_auth.json")


def read_secret(paths: tuple[Path, ...] = SECRET_FILES) -> dict[str, str]:
    for path in paths:
        if not path.is_file():
            continue
        values = dict(
            line.split("=", 1)
            for line in path.read_text(encoding="utf-8").splitlines()
            if "=" in line
        )
        if values.get("username") and values.get("password"):
            return values
    raise RuntimeError("Credencial administrativa valida nao encontrada")


def main() -> int:
    secret = read_secret()
    expected_password_reset = secret.get("change_required", "true").lower() == "true"
    client = TestClient(app)
    wrong = client.post(
        "/api/auth/login",
        json={"username": secret["username"], "password": "credencial-incorreta"},
    )
    empty = client.post("/api/auth/login", json={"username": " ", "password": " "})
    limited_responses = [
        client.post(
            "/api/auth/login",
            json={"username": "rate-limit-validation-user", "password": "invalid"},
        )
        for _ in range(6)
    ]
    login = client.post(
        "/api/auth/login",
        json={"username": secret["username"], "password": secret["password"]},
    )
    login_json = login.json() if login.status_code == 200 else {}
    csrf = login_json.get("csrf_token", "")
    cookie_headers = login.headers.get_list("set-cookie")
    me = client.get("/api/auth/me")
    invalid_csrf = client.post("/api/auth/logout", headers={"X-CSRF-Token": "invalid"})
    logout = client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})
    after_logout = client.get("/api/auth/me")

    settings = get_settings()
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    with Session(engine) as session:
        audit_count = (
            session.scalar(
                select(func.count()).select_from(AuditLog).where(AuditLog.entity_type == "auth")
            )
            or 0
        )
    criteria = {
        "wrong_credentials_rejected": wrong.status_code == 401,
        "blank_credentials_rejected": empty.status_code == 401,
        "login_rate_limit_enforced": limited_responses[-1].status_code == 429,
        "valid_login": login.status_code == 200,
        "session_cookie_httponly": any(
            "abel_session=" in value and "httponly" in value.lower() for value in cookie_headers
        ),
        "cookies_samesite_strict": all(
            "samesite=strict" in value.lower() for value in cookie_headers if "abel_" in value
        ),
        "me_authenticated": me.status_code == 200 and "gerente" in me.json().get("roles", []),
        "invalid_csrf_rejected": invalid_csrf.status_code == 403,
        "logout_succeeds": logout.status_code == 204,
        "revoked_session_rejected": after_logout.status_code == 401,
        "auth_events_audited": audit_count >= 3,
        "password_reset_state_matches_expected":
        login_json.get("must_reset_password") is expected_password_reset,
    }
    result = {
        "generated_at": datetime.now(UTC).isoformat(),
        "criteria": criteria,
        "audit_event_count": audit_count,
        "integrity": "PASS" if all(criteria.values()) else "FAIL",
    }
    OUTPUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["integrity"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
