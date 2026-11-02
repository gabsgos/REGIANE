from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from backend.app.core.config import get_settings
from backend.app.main import create_app
from fastapi.testclient import TestClient

OUTPUT = Path("docs/fase_12_validacao_observabilidade.json")


def main() -> int:
    settings = get_settings()
    marker_username = "sensitive-user-marker"
    marker_password = "sensitive-password-marker"
    client = TestClient(create_app())
    health = client.get("/api/health")
    failed_login = client.post(
        "/api/auth/login",
        json={"username": marker_username, "password": marker_password},
    )
    log_path = Path(settings.log_path)
    content = log_path.read_text(encoding="utf-8")
    parsed = [json.loads(line) for line in content.splitlines() if line.strip()]
    handlers = [
        handler
        for handler in logging.getLogger("abel").handlers
        if isinstance(handler, RotatingFileHandler)
    ]
    criteria = {
        "health_api_database_storage": health.status_code == 200
        and health.json().get("checks")
        == {"api": "ok", "database": "ok", "document_storage": "ok"},
        "failed_login_is_generic": failed_login.status_code == 401,
        "logs_are_json": bool(parsed) and all("timestamp" in item for item in parsed),
        "logs_exclude_credentials": marker_username not in content
        and marker_password not in content,
        "logs_exclude_query_and_body": all(
            "query" not in item and "body" not in item and "headers" not in item for item in parsed
        ),
        "rotation_configured": bool(handlers)
        and handlers[0].maxBytes == settings.log_max_bytes
        and handlers[0].backupCount == settings.log_backup_count,
    }
    result = {
        "generated_at": datetime.now(UTC).isoformat(),
        "log_records_inspected": len(parsed),
        "criteria": criteria,
        "integrity": "PASS" if all(criteria.values()) else "FAIL",
    }
    OUTPUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["integrity"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
