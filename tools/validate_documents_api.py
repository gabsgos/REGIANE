from __future__ import annotations

import json
import secrets
from datetime import UTC, date, datetime
from io import BytesIO
from pathlib import Path

from backend.app.core.config import get_settings
from backend.app.db.models import (
    Appointment,
    AuditLog,
    AuthSession,
    ClinicalDocument,
    Patient,
    Professional,
    User,
    UserRole,
)
from backend.app.main import create_app
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.orm import Session
from tools.validate_clinical_api import create_validation_user, login

OUTPUT = Path("docs/fase_9_validacao_documentos.json")


def make_pdf() -> bytes:
    output = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.write(output)
    return output.getvalue()


def main() -> int:
    settings = get_settings()
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    suffix = secrets.token_hex(5)
    password = secrets.token_urlsafe(18)
    with Session(engine) as session, session.begin():
        professional = Professional(
            name="Profissional documento validacao",
            council_type="CRM",
            council_number=f"DOC-{suffix}",
            active=True,
        )
        patient = Patient(name="Paciente Documento Validacao", active=True)
        session.add_all([professional, patient])
        session.flush()
        appointment = Appointment(
            patient_id=patient.id,
            exam_date=date.today(),
            doctor_id=professional.id,
            status="aberto",
        )
        session.add(appointment)
        session.flush()
        manager = create_validation_user(session, f"doc-manager-{suffix}", password, "gerente")
        doctor = create_validation_user(
            session,
            f"doc-doctor-{suffix}",
            password,
            "medico",
            professional.id,
        )
        attendant = create_validation_user(
            session, f"doc-attendant-{suffix}", password, "atendente"
        )
        user_ids = [manager.id, doctor.id, attendant.id]
        manager_username = manager.username
        doctor_username = doctor.username
        attendant_username = attendant.username
        appointment_id, patient_id, professional_id = (
            appointment.id,
            patient.id,
            professional.id,
        )

    pdf_data = make_pdf()
    manager_client = TestClient(create_app())
    manager_csrf = login(manager_client, manager_username, password)
    invalid = manager_client.post(
        f"/api/documents/appointments/{appointment_id}",
        headers={"X-CSRF-Token": manager_csrf},
        data={"document_type": "laudo"},
        files={"file": ("falso.pdf", b"texto renomeado", "application/pdf")},
    )
    oversized = manager_client.post(
        f"/api/documents/appointments/{appointment_id}",
        headers={"X-CSRF-Token": manager_csrf},
        data={"document_type": "laudo"},
        files={
            "file": (
                "grande.pdf",
                b"%PDF-" + b"0" * settings.document_max_bytes,
                "application/pdf",
            )
        },
    )
    first = manager_client.post(
        f"/api/documents/appointments/{appointment_id}",
        headers={"X-CSRF-Token": manager_csrf},
        data={"document_type": "laudo"},
        files={"file": ("laudo-v1.pdf", pdf_data, "application/pdf")},
    )

    doctor_client = TestClient(create_app())
    doctor_csrf = login(doctor_client, doctor_username, password)
    second = doctor_client.post(
        f"/api/documents/appointments/{appointment_id}",
        headers={"X-CSRF-Token": doctor_csrf},
        data={"document_type": "laudo"},
        files={"file": ("laudo-v2.pdf", pdf_data, "application/pdf")},
    )
    second_json = second.json() if second.status_code == 201 else {}
    document_id = second_json.get("id")
    history = manager_client.get(f"/api/documents/appointments/{appointment_id}")
    download = doctor_client.get(f"/api/documents/{document_id}/download")
    direct_public = manager_client.get(f"/data/documents/{document_id}")

    attendant_client = TestClient(create_app())
    login(attendant_client, attendant_username, password)
    denied = attendant_client.get(f"/api/documents/{document_id}/download")

    with Session(engine) as session:
        document = session.get(ClinicalDocument, document_id)
        target = Path(settings.document_storage_path).resolve() / document.storage_key
        original_bytes = target.read_bytes()
        target.write_bytes(original_bytes + b"tamper")
    tampered = manager_client.get(f"/api/documents/{document_id}/download")
    target.write_bytes(original_bytes)
    restarted_client = TestClient(create_app())
    login(restarted_client, manager_username, password)
    persisted = restarted_client.get(f"/api/documents/{document_id}/download")

    history_items = history.json().get("items", []) if history.status_code == 200 else []
    versions = sorted(item.get("version") for item in history_items)
    active_count = sum(bool(item.get("active")) for item in history_items)
    with Session(engine) as session:
        audit_count = (
            session.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.entity_type == "clinical_documents")
            )
            or 0
        )
        documents = list(
            session.scalars(
                select(ClinicalDocument).where(ClinicalDocument.appointment_id == appointment_id)
            )
        )

    criteria = {
        "renamed_non_pdf_rejected": invalid.status_code == 422,
        "size_limit_enforced": oversized.status_code == 413,
        "first_version_uploaded": first.status_code == 201,
        "doctor_assigned_can_upload": second.status_code == 201,
        "version_history_preserved": versions == [1, 2] and active_count == 1,
        "authenticated_download": download.status_code == 200 and download.content == pdf_data,
        "no_public_direct_url": direct_public.status_code == 404,
        "unauthorized_profile_denied": denied.status_code == 403,
        "hash_detects_tamper": tampered.status_code == 409,
        "persists_after_new_app_instance": persisted.status_code == 200
        and persisted.content == pdf_data,
        "document_actions_audited": audit_count >= 4,
    }
    result = {
        "generated_at": datetime.now(UTC).isoformat(),
        "criteria": criteria,
        "versions": versions,
        "audit_events": audit_count,
        "integrity": "PASS" if all(criteria.values()) else "FAIL",
    }

    with Session(engine) as session, session.begin():
        document_ids = [item.id for item in documents]
        if document_ids:
            session.execute(delete(ClinicalDocument).where(ClinicalDocument.id.in_(document_ids)))
            session.execute(
                delete(AuditLog).where(
                    AuditLog.entity_type == "clinical_documents",
                    AuditLog.entity_id.in_([str(item) for item in document_ids]),
                )
            )
        session.execute(delete(AuditLog).where(AuditLog.user_id.in_(user_ids)))
        session.execute(delete(AuthSession).where(AuthSession.user_id.in_(user_ids)))
        session.execute(delete(UserRole).where(UserRole.user_id.in_(user_ids)))
        session.execute(delete(User).where(User.id.in_(user_ids)))
        session.execute(delete(Appointment).where(Appointment.id == appointment_id))
        session.execute(delete(Patient).where(Patient.id == patient_id))
        session.execute(delete(Professional).where(Professional.id == professional_id))
    for item in documents:
        file_path = (Path(settings.document_storage_path).resolve() / item.storage_key).resolve()
        if file_path.parent == Path(settings.document_storage_path).resolve():
            file_path.unlink(missing_ok=True)

    OUTPUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["integrity"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
