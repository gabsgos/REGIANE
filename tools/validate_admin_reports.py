from __future__ import annotations

import json
import secrets
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path

from backend.app.core.config import get_settings
from backend.app.db.models import (
    Appointment,
    AuditLog,
    AuthSession,
    Patient,
    Payment,
    PaymentItem,
    Receipt,
    User,
    UserRole,
)
from backend.app.main import create_app
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.orm import Session
from tools.validate_clinical_api import create_validation_user, login

OUTPUT = Path("docs/fase_11_validacao_admin_relatorios.json")


def main() -> int:
    settings = get_settings()
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    suffix = secrets.token_hex(5)
    password = secrets.token_urlsafe(18)
    today = date.today()
    now = datetime.now(UTC).replace(tzinfo=None)
    with Session(engine) as session, session.begin():
        manager = create_validation_user(session, f"report-manager-{suffix}", password, "gerente")
        attendant = create_validation_user(
            session, f"report-attendant-{suffix}", password, "atendente"
        )
        patient = Patient(name="=FORMULA_VALIDATION", active=True)
        session.add(patient)
        session.flush()
        appointment = Appointment(patient_id=patient.id, exam_date=today, status="concluido")
        session.add(appointment)
        session.flush()
        payment = Payment(
            appointment_id=appointment.id,
            total_amount=Decimal("55.00"),
            status="pago",
            paid_at=now,
            created_by_id=manager.id,
        )
        receipt = Receipt(
            receipt_number=f"REPORT-{suffix}",
            appointment_id=appointment.id,
            patient_id=patient.id,
            issued_at=today,
            amount=Decimal("55.00"),
        )
        session.add_all([payment, receipt])
        session.flush()
        session.add(PaymentItem(payment_id=payment.id, method="pix", amount=Decimal("55.00")))
        manager_id, attendant_id = manager.id, attendant.id
        patient_id, appointment_id, payment_id, receipt_id = (
            patient.id,
            appointment.id,
            payment.id,
            receipt.id,
        )
        manager_username, attendant_username = manager.username, attendant.username

    manager_client = TestClient(create_app())
    manager_csrf = login(manager_client, manager_username, password)
    created_user = manager_client.post(
        "/api/admin/users",
        headers={"X-CSRF-Token": manager_csrf},
        json={
            "username": f"created-{suffix}",
            "display_name": "Usuario Criado Validacao",
            "role": "atendente",
        },
    )
    created_json = created_user.json() if created_user.status_code == 201 else {}
    created_user_id = created_json.get("user", {}).get("id")
    temp_password = created_json.get("temporary_password", "")
    users_list = manager_client.get("/api/admin/users")
    reset = manager_client.post(
        f"/api/admin/users/{created_user_id}/reset-password",
        headers={"X-CSRF-Token": manager_csrf},
    )

    params = {"date_from": today.isoformat(), "date_to": today.isoformat()}
    report = manager_client.get("/api/reports/appointments", params=params)
    export = manager_client.get("/api/reports/appointments.csv", params=params)
    closing = manager_client.get(
        "/api/reports/daily-closing", params={"closing_date": today.isoformat()}
    )
    issues = manager_client.get("/api/reports/migration-issues")

    attendant_client = TestClient(create_app())
    login(attendant_client, attendant_username, password)
    attendant_users = attendant_client.get("/api/admin/users")
    attendant_report = attendant_client.get("/api/reports/appointments", params=params)

    start = datetime.combine(today, time.min)
    end = start + timedelta(days=1)
    with Session(engine) as session:
        independent_appointments = (
            session.scalar(
                select(func.count()).select_from(Appointment).where(Appointment.exam_date == today)
            )
            or 0
        )
        independent_paid = session.scalar(
            select(func.sum(Payment.total_amount)).where(
                Payment.status == "pago", Payment.paid_at >= start, Payment.paid_at < end
            )
        ) or Decimal("0.00")
        independent_receipts = session.scalar(
            select(func.sum(Receipt.amount)).where(Receipt.issued_at == today)
        ) or Decimal("0.00")
        new_user = session.get(User, created_user_id) if created_user_id else None
        export_audit = (
            session.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.user_id == manager_id, AuditLog.action == "export")
            )
            or 0
        )

    report_json = report.json() if report.status_code == 200 else {}
    closing_json = closing.json() if closing.status_code == 200 else {}
    csv_text = export.content.decode("utf-8-sig") if export.status_code == 200 else ""
    criteria = {
        "manager_creates_user": created_user.status_code == 201
        and bool(temp_password)
        and new_user is not None
        and (new_user.password_hash or "").startswith("$argon2"),
        "temporary_password_reset": reset.status_code == 200
        and reset.json().get("temporary_password") != temp_password,
        "user_list_manager_only": users_list.status_code == 200
        and attendant_users.status_code == 403,
        "report_matches_control_query": report.status_code == 200
        and report_json.get("appointment_count") == independent_appointments,
        "closing_matches_control_queries": closing.status_code == 200
        and Decimal(closing_json.get("paid_total", "0")) == independent_paid
        and Decimal(closing_json.get("receipt_total", "0")) == independent_receipts,
        "csv_export_authorized_and_safe": export.status_code == 200
        and "text/csv" in export.headers.get("content-type", "")
        and "'=FORMULA_VALIDATION" in csv_text,
        "export_audited": export_audit >= 1,
        "migration_panel_available": issues.status_code == 200
        and issues.json().get("total") == 510,
        "attendant_report_denied": attendant_report.status_code == 403,
    }
    result = {
        "generated_at": datetime.now(UTC).isoformat(),
        "criteria": criteria,
        "report_appointment_count": report_json.get("appointment_count"),
        "control_appointment_count": independent_appointments,
        "integrity": "PASS" if all(criteria.values()) else "FAIL",
    }

    cleanup_user_ids = [manager_id, attendant_id] + ([created_user_id] if created_user_id else [])
    with Session(engine) as session, session.begin():
        session.execute(delete(AuditLog).where(AuditLog.user_id.in_(cleanup_user_ids)))
        session.execute(delete(AuthSession).where(AuthSession.user_id.in_(cleanup_user_ids)))
        session.execute(delete(UserRole).where(UserRole.user_id.in_(cleanup_user_ids)))
        session.execute(delete(PaymentItem).where(PaymentItem.payment_id == payment_id))
        session.execute(delete(Receipt).where(Receipt.id == receipt_id))
        session.execute(delete(Payment).where(Payment.id == payment_id))
        session.execute(delete(Appointment).where(Appointment.id == appointment_id))
        session.execute(delete(User).where(User.id.in_(cleanup_user_ids)))
        session.execute(delete(Patient).where(Patient.id == patient_id))

    OUTPUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["integrity"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
