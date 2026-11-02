from __future__ import annotations

import json
import secrets
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from pathlib import Path
from threading import Barrier

from backend.app.core.config import get_settings
from backend.app.db.models import (
    Appointment,
    AuditLog,
    AuthSession,
    Patient,
    User,
    UserRole,
)
from backend.app.main import create_app
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import Session
from tools.validate_clinical_api import create_validation_user, login

OUTPUT = Path("docs/fase_13_concorrencia_desempenho.json")


def main() -> int:
    settings = get_settings()
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    suffix = secrets.token_hex(5)
    username = f"concurrency-{suffix}"
    password = secrets.token_urlsafe(18)
    with Session(engine) as session, session.begin():
        user = create_validation_user(session, username, password, "gerente")
        patient = Patient(name="Paciente Concorrencia", active=True)
        session.add(patient)
        session.flush()
        appointment = Appointment(patient_id=patient.id, exam_date=date.today(), status="aberto")
        session.add(appointment)
        session.flush()
        user_id, patient_id, appointment_id = user.id, patient.id, appointment.id

    clients = [TestClient(create_app()), TestClient(create_app())]
    csrf_tokens = [login(client, username, password) for client in clients]
    barrier = Barrier(2)

    def competing_update(index: int) -> int:
        barrier.wait()
        response = clients[index].put(
            f"/api/appointments/{appointment_id}",
            headers={"X-CSRF-Token": csrf_tokens[index]},
            json={
                "patient_id": patient_id,
                "exam_date": date.today().isoformat(),
                "status": "concluido" if index == 0 else "cancelado",
                "expected_version": 1,
            },
        )
        return response.status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses = sorted(executor.map(competing_update, range(2)))

    performance_client = clients[0]

    def timed_request(_: int) -> float:
        started = time.perf_counter()
        response = performance_client.get("/api/appointments", params={"page_size": 25})
        if response.status_code != 200:
            raise RuntimeError(f"consulta falhou: {response.status_code}")
        return (time.perf_counter() - started) * 1000

    with ThreadPoolExecutor(max_workers=8) as executor:
        durations = list(executor.map(timed_request, range(40)))
    sorted_durations = sorted(durations)
    p95 = sorted_durations[int(len(sorted_durations) * 0.95) - 1]
    criteria = {
        "one_update_wins_one_conflicts": statuses == [200, 409],
        "forty_concurrent_queries_succeed": len(durations) == 40,
        "p95_under_1000ms": p95 < 1000,
    }
    result = {
        "generated_at": datetime.now(UTC).isoformat(),
        "database": engine.url.database,
        "update_statuses": statuses,
        "request_count": len(durations),
        "mean_ms": round(statistics.mean(durations), 3),
        "p95_ms": round(p95, 3),
        "max_ms": round(max(durations), 3),
        "criteria": criteria,
        "integrity": "PASS" if all(criteria.values()) else "FAIL",
    }
    with Session(engine) as session, session.begin():
        session.execute(delete(AuditLog).where(AuditLog.user_id == user_id))
        session.execute(delete(AuthSession).where(AuthSession.user_id == user_id))
        session.execute(delete(UserRole).where(UserRole.user_id == user_id))
        session.execute(delete(Appointment).where(Appointment.id == appointment_id))
        session.execute(delete(User).where(User.id == user_id))
        session.execute(delete(Patient).where(Patient.id == patient_id))
    OUTPUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["integrity"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
