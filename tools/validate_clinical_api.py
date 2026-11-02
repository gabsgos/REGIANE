from __future__ import annotations

import json
import secrets
from datetime import UTC, date, datetime
from pathlib import Path

from backend.app.core.config import get_settings
from backend.app.core.security import hash_password
from backend.app.db.models import (
    Appointment,
    AuditLog,
    AuthSession,
    Patient,
    Professional,
    Role,
    User,
    UserRole,
)
from backend.app.main import create_app
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.orm import Session

OUTPUT = Path("docs/fase_7_validacao_api.json")


def create_validation_user(
    session: Session,
    username: str,
    password: str,
    role_name: str,
    professional_id: int | None = None,
) -> User:
    role = session.scalar(select(Role).where(Role.name == role_name))
    if not role:
        raise RuntimeError(f"perfil ausente: {role_name}")
    user = User(
        username=username,
        display_name=f"Validacao {role_name}",
        password_hash=hash_password(password),
        professional_id=professional_id,
        active=True,
        must_reset_password=False,
    )
    session.add(user)
    session.flush()
    session.add(UserRole(user_id=user.id, role_id=role.id))
    return user


def login(client: TestClient, username: str, password: str) -> str:
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    if response.status_code != 200:
        raise RuntimeError(f"login de validacao falhou: {response.status_code}")
    return response.json()["csrf_token"]


def main() -> int:
    settings = get_settings()
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    suffix = secrets.token_hex(5)
    manager_name = f"validation-manager-{suffix}"
    doctor_name = f"validation-doctor-{suffix}"
    manager_password = secrets.token_urlsafe(18)
    doctor_password = secrets.token_urlsafe(18)
    with Session(engine) as session, session.begin():
        professional = Professional(
            name="Profissional de validacao",
            council_type="CRM",
            council_number=f"VAL-{suffix}",
            active=True,
        )
        session.add(professional)
        session.flush()
        manager = create_validation_user(session, manager_name, manager_password, "gerente")
        doctor = create_validation_user(
            session, doctor_name, doctor_password, "medico", professional.id
        )
        manager_id, doctor_id, professional_id = manager.id, doctor.id, professional.id

    manager_client = TestClient(create_app())
    manager_csrf = login(manager_client, manager_name, manager_password)
    patient_response = manager_client.post(
        "/api/patients",
        headers={"X-CSRF-Token": manager_csrf},
        json={"name": "Paciente Validacao Persistencia"},
    )
    patient_json = patient_response.json() if patient_response.status_code == 201 else {}
    patient_id = patient_json.get("id")
    assigned_response = manager_client.post(
        "/api/appointments",
        headers={"X-CSRF-Token": manager_csrf},
        json={
            "patient_id": patient_id,
            "exam_date": date.today().isoformat(),
            "doctor_id": professional_id,
        },
    )
    assigned = assigned_response.json() if assigned_response.status_code == 201 else {}
    unassigned_response = manager_client.post(
        "/api/appointments",
        headers={"X-CSRF-Token": manager_csrf},
        json={"patient_id": patient_id, "exam_date": date.today().isoformat()},
    )
    unassigned = unassigned_response.json() if unassigned_response.status_code == 201 else {}
    update_payload = {
        "patient_id": patient_id,
        "exam_date": date.today().isoformat(),
        "doctor_id": professional_id,
        "status": "concluido",
        "expected_version": assigned.get("row_version", 1),
    }
    updated_response = manager_client.put(
        f"/api/appointments/{assigned.get('id')}",
        headers={"X-CSRF-Token": manager_csrf},
        json=update_payload,
    )
    stale_response = manager_client.put(
        f"/api/appointments/{assigned.get('id')}",
        headers={"X-CSRF-Token": manager_csrf},
        json=update_payload,
    )

    restarted_client = TestClient(create_app())
    login(restarted_client, manager_name, manager_password)
    persisted_response = restarted_client.get(f"/api/appointments/{assigned.get('id')}")

    doctor_client = TestClient(create_app())
    doctor_csrf = login(doctor_client, doctor_name, doctor_password)
    doctor_list = doctor_client.get(
        "/api/appointments", params={"search": "Paciente Validacao", "page_size": 100}
    )
    doctor_forbidden_create = doctor_client.post(
        "/api/patients",
        headers={"X-CSRF-Token": doctor_csrf},
        json={"name": "Nao deve criar"},
    )

    with Session(engine) as session:
        audit_count = (
            session.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(
                    AuditLog.user_id == manager_id,
                    AuditLog.entity_type.in_(["patients", "appointments"]),
                )
            )
            or 0
        )

    criteria = {
        "patient_created": patient_response.status_code == 201,
        "appointments_created": assigned_response.status_code == 201
        and unassigned_response.status_code == 201,
        "optimistic_update_succeeds": updated_response.status_code == 200
        and updated_response.json().get("row_version") == 2,
        "stale_update_rejected": stale_response.status_code == 409,
        "persistence_after_new_app_instance": persisted_response.status_code == 200
        and persisted_response.json().get("status") == "concluido",
        "doctor_scope_composed_with_search": doctor_list.status_code == 200
        and doctor_list.json().get("total") == 1,
        "doctor_cannot_create_patient": doctor_forbidden_create.status_code == 403,
        "changes_audited": audit_count >= 4,
    }
    result = {
        "generated_at": datetime.now(UTC).isoformat(),
        "criteria": criteria,
        "audit_events": audit_count,
        "integrity": "PASS" if all(criteria.values()) else "FAIL",
    }

    with Session(engine) as session, session.begin():
        appointment_ids = [item for item in (assigned.get("id"), unassigned.get("id")) if item]
        if appointment_ids:
            session.execute(
                delete(AuditLog).where(
                    AuditLog.entity_type == "appointments",
                    AuditLog.entity_id.in_([str(item) for item in appointment_ids]),
                )
            )
            session.execute(delete(Appointment).where(Appointment.id.in_(appointment_ids)))
        if patient_id:
            session.execute(
                delete(AuditLog).where(
                    AuditLog.entity_type == "patients", AuditLog.entity_id == str(patient_id)
                )
            )
            session.execute(delete(Patient).where(Patient.id == patient_id))
        session.execute(delete(AuditLog).where(AuditLog.user_id.in_([manager_id, doctor_id])))
        session.execute(delete(AuthSession).where(AuthSession.user_id.in_([manager_id, doctor_id])))
        session.execute(delete(UserRole).where(UserRole.user_id.in_([manager_id, doctor_id])))
        session.execute(delete(User).where(User.id.in_([manager_id, doctor_id])))
        session.execute(delete(Professional).where(Professional.id == professional_id))

    OUTPUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["integrity"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
