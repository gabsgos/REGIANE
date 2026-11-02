from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

from backend.app.main import create_app
from fastapi.testclient import TestClient

OUTPUT = Path("docs/smoke_test_result.json")


def main() -> int:
    username = os.getenv("ABEL_SMOKE_USERNAME")
    password = os.getenv("ABEL_SMOKE_PASSWORD")
    if not username or not password:
        raise RuntimeError("ABEL_SMOKE_USERNAME e ABEL_SMOKE_PASSWORD sao obrigatorios")
    client = TestClient(create_app())
    health = client.get("/api/health")
    root = client.get("/")
    login = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    me = client.get("/api/auth/me") if login.status_code == 200 else None
    appointments = client.get("/api/appointments", params={"page_size": 1}) if me else None
    criteria = {
        "health": health.status_code == 200 and health.json().get("status") == "ok",
        "frontend": root.status_code == 200,
        "login": login.status_code == 200,
        "session": me is not None and me.status_code == 200,
        "appointments_read": appointments is not None and appointments.status_code == 200,
    }
    result = {
        "generated_at": datetime.now(UTC).isoformat(),
        "criteria": criteria,
        "integrity": "PASS" if all(criteria.values()) else "FAIL",
    }
    OUTPUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["integrity"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
